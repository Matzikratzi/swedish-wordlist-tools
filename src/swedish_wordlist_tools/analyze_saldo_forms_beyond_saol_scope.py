from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

DEFAULT_INPUT = Path("reports/saol14-direct-form-validation.jsonl")
DEFAULT_JSONL = Path("reports/saol14-saldo-forms-beyond-saol-scope.jsonl")
DEFAULT_TEXT = Path("reports/saol14-saldo-forms-beyond-saol-scope.txt")


def _relative(lemma: str, form: object) -> str:
    lemma_cf = lemma.casefold()
    form_cf = str(form).casefold()
    if lemma_cf and form_cf.startswith(lemma_cf):
        return "+" + form_cf[len(lemma_cf):]
    return "=" + form_cf


def _plural_like(row: dict[str, Any], form: str) -> bool:
    # Prefer SALDO's form metadata if it is available in a future artifact.
    # The current direct-validation artifact contains only written forms, so
    # compare against the SAOL-generated singular inventory conservatively.
    lemma = str(row.get("lemma") or "").casefold()
    generated = {str(value).casefold() for value in row.get("generated_forms", ())}
    singular = {
        lemma,
        lemma + "s",
    }
    singular.update(
        value for value in generated
        if value == lemma or value == lemma + "s"
        or value in {str(x).casefold() for x in row.get("extra_from_saol", ())}
    )
    return form.casefold() not in singular and form.casefold() not in generated


def candidates(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in rows:
        if str(row.get("upos") or "").upper() != "NOUN":
            continue
        notation = str(row.get("notation") or "").strip()
        # First, deliberately narrow audit: SAOL supplies only definite
        # singular.  There is no plural slot/instruction to license plural
        # completion.  These are the kyrkofrid/fostbrödraskap-shaped cases.
        if notation not in {"+en", "+et", "+n", "+t"}:
            continue
        saldo = [str(value) for value in row.get("saldo_forms", ())]
        generated = {str(value).casefold() for value in row.get("generated_forms", ())}
        saldo_only = [value for value in saldo if value.casefold() not in generated]
        if not saldo_only:
            continue
        suspicious = [value for value in saldo_only if _plural_like(row, value)]
        if not suspicious:
            continue
        lemma = str(row.get("lemma") or "")
        result.append({
            "lemma": lemma,
            "homonym_number": str(row.get("homonym_number") or ""),
            "record_id": str(row.get("record_id") or ""),
            "notation": notation,
            "generated_forms": list(row.get("generated_forms", ())),
            "saldo_forms": saldo,
            "saldo_only": saldo_only,
            "saldo_only_relative": sorted(_relative(lemma, value) for value in saldo_only),
            "match_method": str(row.get("match_method") or ""),
            "status": str(row.get("status") or ""),
        })
    result.sort(key=lambda row: (row["notation"], row["lemma"].casefold(), row["homonym_number"]))
    return result


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def render(rows: list[dict[str, Any]]) -> str:
    by_notation = Counter(row["notation"] for row in rows)
    grouped: dict[tuple[str, tuple[str, ...]], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["notation"], tuple(row["saldo_only_relative"]))].append(row)
    groups = sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0]))
    lines = [
        "SALDO-former utanför explicit SAOL-paradigmomfång",
        "",
        "Urval: NOUN där SAOL-notationen bara anger bestämd singular (+en/+et/+n/+t),",
        "men SALDO har ytterligare former som SAOL-generatorn inte genererar.",
        "Detta är en audit, inte en automatisk klassificering av formernas grammatiska funktion.",
        "",
        f"Poster: {len(rows)}",
        "",
        "Notationer:",
    ]
    for notation, count in by_notation.most_common():
        lines.append(f"{count:5}  {notation}")
    lines.extend(["", "Största exakta SALDO-extra-mönster:"])
    for index, ((notation, pattern), members) in enumerate(groups[:40], start=1):
        examples = ", ".join(row["lemma"] for row in members[:12])
        lines.extend([
            "",
            f"{index}. {len(members)} | {notation}",
            f"   SALDO-extra: {', '.join(pattern)}",
            f"   Exempel: {examples}",
        ])
    lines.extend(["", "För manuell kontroll på svenska.se:"])
    for row in rows[:80]:
        lines.append(
            f"  {row['lemma']} ({row['homonym_number'] or '-'}) | {row['notation']} | "
            f"SAOL-gen: {', '.join(row['generated_forms'])} | SALDO-extra: {', '.join(row['saldo_only'])}"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    args = parser.parse_args()
    rows = candidates(read_jsonl(args.input))
    write_jsonl(args.jsonl, rows)
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render(rows), encoding="utf-8")
    print(f"Poster: {len(rows)}")
    print(f"Text: {args.text}")
    print(f"JSONL: {args.jsonl}")


if __name__ == "__main__":
    main()
