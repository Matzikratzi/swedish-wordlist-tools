from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

DEFAULT_INPUT = Path("reports/saol14-direct-form-validation.jsonl")
DEFAULT_TEXT = Path("reports/saol14-singular-agreement-for-scope-extras.txt")
DEFAULT_JSON = Path("reports/saol14-singular-agreement-for-scope-extras.json")
SINGULAR_ONLY = {"+en", "+et", "+n", "+t"}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _cf(values: Iterable[object]) -> set[str]:
    return {str(value).casefold() for value in values}


def _relative(lemma: str, form: object) -> str:
    word = str(form).casefold()
    base = lemma.casefold()
    if base and word.startswith(base):
        return "+" + word[len(base):]
    return "=" + word


def candidates(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in rows:
        if str(row.get("upos") or "").upper() != "NOUN":
            continue
        notation = str(row.get("notation") or "").strip()
        if notation not in SINGULAR_ONLY:
            continue

        generated = _cf(row.get("generated_forms", ()))
        saldo = _cf(row.get("saldo_forms", ()))
        if not generated or not saldo:
            continue

        saldo_extra = sorted(saldo - generated)
        if not saldo_extra:
            continue

        # For singular-only SAOL articles every generated form belongs to the
        # article's licensed singular paradigm.  Agreement therefore means that
        # SALDO contains the entire SAOL singular inventory, regardless of any
        # additional SALDO forms (often extrapolated plural).
        missing_singular = sorted(generated - saldo)
        singular_status = "singular_exact" if not missing_singular else "singular_mismatch"
        lemma = str(row.get("lemma") or "")
        result.append({
            "lemma": lemma,
            "homonym_number": str(row.get("homonym_number") or ""),
            "record_id": str(row.get("record_id") or ""),
            "notation": notation,
            "validation_status": str(row.get("status") or ""),
            "singular_status": singular_status,
            "saol_singular": sorted(generated),
            "saldo_forms": sorted(saldo),
            "saldo_extra": saldo_extra,
            "saldo_extra_relative": sorted(_relative(lemma, value) for value in saldo_extra),
            "missing_singular": missing_singular,
            "missing_singular_relative": sorted(_relative(lemma, value) for value in missing_singular),
            "match_method": str(row.get("match_method") or ""),
        })
    result.sort(key=lambda item: (item["singular_status"], item["notation"], item["lemma"].casefold(), item["homonym_number"]))
    return result


def build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(row["singular_status"] for row in rows)
    validation_counts = Counter(row["validation_status"] for row in rows)
    notation_counts = Counter((row["notation"], row["singular_status"]) for row in rows)
    mismatch_groups: dict[tuple[str, tuple[str, ...], tuple[str, ...]], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["singular_status"] != "singular_mismatch":
            continue
        mismatch_groups[(
            row["notation"],
            tuple(row["missing_singular_relative"]),
            tuple(row["saldo_extra_relative"]),
        )].append(row)
    ordered = sorted(mismatch_groups.items(), key=lambda item: (-len(item[1]), item[0]))
    return {
        "records": len(rows),
        "singular_status_counts": dict(status_counts.most_common()),
        "validation_status_counts": dict(validation_counts.most_common()),
        "notation_status_counts": [
            {"notation": notation, "singular_status": singular_status, "count": count}
            for (notation, singular_status), count in sorted(notation_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        "mismatch_groups": [
            {
                "notation": key[0],
                "missing_singular": list(key[1]),
                "saldo_extra": list(key[2]),
                "count": len(members),
                "examples": [
                    {"lemma": row["lemma"], "homonym_number": row["homonym_number"]}
                    for row in members[:20]
                ],
            }
            for key, members in ordered
        ],
        "rows": rows,
    }


def render(summary: dict[str, Any]) -> str:
    lines = [
        "SAOL14: singularöverensstämmelse när SALDO går utanför artikelomfånget",
        "",
        "Population: NOUN med singular-only-notation (+en/+et/+n/+t) där SALDO",
        "har ytterligare former. SAOL-generatorns hela formmängd är då singularparadigmet.",
        "",
        f"Poster: {summary['records']}",
        "",
        "Singularstatus:",
    ]
    for name, count in summary["singular_status_counts"].items():
        lines.append(f"{count:5}  {name}")
    lines.extend(["", "Nuvarande valideringsstatus:"])
    for name, count in summary["validation_status_counts"].items():
        lines.append(f"{count:5}  {name or '(tomt)'}")
    lines.extend(["", "Per notation och singularstatus:"])
    for item in summary["notation_status_counts"]:
        lines.append(f"{item['count']:5}  {item['notation']}  {item['singular_status']}")
    lines.extend(["", "Singularmismatchar, största exakta grupper:"])
    for index, group in enumerate(summary["mismatch_groups"][:50], start=1):
        examples = ", ".join(
            item["lemma"] + (f" ({item['homonym_number']})" if item["homonym_number"] else "")
            for item in group["examples"][:12]
        )
        lines.extend([
            "",
            f"{index}. {group['count']} | {group['notation']}",
            f"   SAOL-singular saknas i SALDO: {', '.join(group['missing_singular'])}",
            f"   SALDO-extra: {', '.join(group['saldo_extra'])}",
            f"   Exempel: {examples}",
        ])
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()
    rows = candidates(read_jsonl(args.input))
    summary = build_summary(rows)
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render(summary), encoding="utf-8")
    args.json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Poster: {summary['records']}")
    for name, count in summary["singular_status_counts"].items():
        print(f"{name}: {count}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
