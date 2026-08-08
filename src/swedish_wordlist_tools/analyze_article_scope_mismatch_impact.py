from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

DEFAULT_INPUT = Path("reports/saol14-form-mismatch-classification.jsonl")
DEFAULT_TEXT = Path("reports/saol14-article-scope-mismatch-impact.txt")
DEFAULT_JSON = Path("reports/saol14-article-scope-mismatch-impact.json")

SINGULAR_ONLY = {"+en", "+et", "+n", "+t"}
PLURAL_SUFFIXES = (
    "ar", "arna", "arnas", "ars",
    "er", "erna", "ernas", "ers",
    "or", "orna", "ornas", "ors",
    "r", "rna", "rnas", "rs",
    "n", "na", "nas", "ns",
)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _relative(lemma: str, form: object) -> str:
    word = str(form)
    if lemma and word.casefold().startswith(lemma.casefold()):
        return "+" + word[len(lemma):]
    return "=" + word


def _looks_like_plural_extra(lemma: str, form: str) -> bool:
    folded = form.casefold()
    base = lemma.casefold()
    if not base or not folded.startswith(base):
        return False
    suffix = folded[len(base):]
    return suffix in PLURAL_SUFFIXES


def candidates(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in rows:
        if str(row.get("mismatch_classification") or "") != "unclassified":
            continue
        if str(row.get("upos") or "").upper() != "NOUN":
            continue
        notation = str(row.get("notation") or "").strip()
        if notation not in SINGULAR_ONLY:
            continue
        lemma = str(row.get("lemma") or "")
        # In mismatch-classification rows, extra_from_saol means forms produced by
        # the SAOL artifact but absent from SALDO, while missing_from_saol are
        # forms SALDO has beyond SAOL.  Article-scope candidates therefore have
        # no SAOL extras and only SALDO-side extras that look like ordinary
        # plural slots.
        extra_saol = [str(v) for v in row.get("extra_from_saol", ())]
        saldo_extra = [str(v) for v in row.get("missing_from_saol", ())]
        if extra_saol or not saldo_extra:
            continue
        if not all(_looks_like_plural_extra(lemma, form) for form in saldo_extra):
            continue
        result.append({
            "lemma": lemma,
            "homonym_number": str(row.get("homonym_number") or ""),
            "record_id": str(row.get("record_id") or ""),
            "notation": notation,
            "saldo_extra": saldo_extra,
            "saldo_extra_relative": sorted(_relative(lemma, form) for form in saldo_extra),
            "match_method": str(row.get("match_method") or ""),
            "coverage_status": str(row.get("coverage_status") or row.get("variant_coverage") or ""),
            "paradigm_reason": str(row.get("paradigm_reason") or ""),
        })
    result.sort(key=lambda item: (item["notation"], item["lemma"].casefold(), item["homonym_number"]))
    return result


def build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    notation_counts = Counter(row["notation"] for row in rows)
    groups: dict[tuple[str, tuple[str, ...]], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row["notation"], tuple(row["saldo_extra_relative"]))].append(row)
    ordered = sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))
    return {
        "records": len(rows),
        "notation_counts": dict(notation_counts.most_common()),
        "groups": [
            {
                "notation": key[0],
                "saldo_extra_pattern": list(key[1]),
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
        "SAOL14 artikelomfång: påverkan på oklassificerade NOUN-mismatchar",
        "",
        "Urval: oklassificerad NOUN, artikelnotation endast +en/+et/+n/+t,",
        "inga SAOL-extraformer och endast SALDO-extraformer som ser ut som plural.",
        "",
        f"Poster: {summary['records']}",
        "",
        "Notationer:",
    ]
    for notation, count in summary["notation_counts"].items():
        lines.append(f"{count:5}  {notation}")
    lines.extend(["", "Största exakta grupper:"])
    for index, group in enumerate(summary["groups"][:50], start=1):
        examples = ", ".join(
            f"{item['lemma']} ({item['homonym_number'] or '-'})"
            for item in group["examples"][:12]
        )
        lines.extend([
            "",
            f"{index}. {group['count']} | {group['notation']}",
            f"   SALDO-extra: {', '.join(group['saldo_extra_pattern'])}",
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
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
