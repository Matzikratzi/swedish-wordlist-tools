from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

DEFAULT_INPUT = Path("reports/saol14-direct-form-validation.jsonl")
DEFAULT_TEXT = Path("reports/saol14-remaining-noun-conflicts-reanalysis.txt")
DEFAULT_JSON = Path("reports/saol14-remaining-noun-conflicts-reanalysis.json")
SINGULAR_ONLY = {"+en", "+et", "+n", "+t"}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _relative(lemma: str, form: object) -> str:
    word = str(form).casefold()
    base = lemma.casefold()
    if base and word.startswith(base):
        return "+" + word[len(base):]
    return "=" + word


def _scope_singular_mismatch(row: dict[str, Any]) -> bool:
    if str(row.get("notation") or "").strip() not in SINGULAR_ONLY:
        return False
    generated = {str(v).casefold() for v in row.get("generated_forms", ())}
    saldo = {str(v).casefold() for v in row.get("saldo_forms", ())}
    return bool(saldo - generated) and bool(generated - saldo)


def classify(row: dict[str, Any]) -> str:
    lemma = str(row.get("lemma") or "")
    extra = [_relative(lemma, v) for v in row.get("extra_from_saol", ())]
    missing = [_relative(lemma, v) for v in row.get("missing_from_saol", ())]

    if _scope_singular_mismatch(row):
        return "singular_scope_conflict"
    if any(value.startswith("=") for value in extra + missing):
        return "variant_or_orthography_conflict"
    if extra and not missing:
        return "saol_only_forms_missing_in_saldo"
    if extra and missing:
        return "competing_form_sets"
    if missing and not extra:
        return "saldo_only_forms"
    return "empty_difference"


def analyze(rows: list[dict[str, Any]]) -> dict[str, Any]:
    selected = [
        row for row in rows
        if str(row.get("upos") or "").upper() == "NOUN"
        and str(row.get("status") or "") == "form_set_mismatch"
    ]
    buckets = Counter()
    notation_counts: dict[str, Counter[str]] = defaultdict(Counter)
    groups: dict[tuple[str, str, tuple[str, ...], tuple[str, ...]], list[dict[str, Any]]] = defaultdict(list)

    for row in selected:
        bucket = classify(row)
        buckets[bucket] += 1
        notation = str(row.get("notation") or "")
        notation_counts[bucket][notation] += 1
        lemma = str(row.get("lemma") or "")
        extra = tuple(sorted(_relative(lemma, v) for v in row.get("extra_from_saol", ())))
        missing = tuple(sorted(_relative(lemma, v) for v in row.get("missing_from_saol", ())))
        groups[(bucket, notation, extra, missing)].append(row)

    ordered = sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))
    return {
        "records": len(selected),
        "bucket_counts": dict(buckets.most_common()),
        "notation_counts": {
            bucket: dict(counter.most_common(20)) for bucket, counter in notation_counts.items()
        },
        "groups": [
            {
                "bucket": key[0],
                "notation": key[1],
                "saol_only": list(key[2]),
                "saldo_only": list(key[3]),
                "count": len(members),
                "examples": [
                    {
                        "lemma": str(row.get("lemma") or ""),
                        "homonym_number": str(row.get("homonym_number") or ""),
                    }
                    for row in members[:15]
                ],
            }
            for key, members in ordered
        ],
    }


def render(summary: dict[str, Any]) -> str:
    lines = [
        "SAOL14 NOUN: omanalys av återstående formkonflikter",
        "",
        "Urval: NOUN med status form_set_mismatch. Inga gamla mismatch-klasser används.",
        f"Poster: {summary['records']}",
        "",
        "Sakliga huvudgrupper:",
    ]
    for name, count in summary["bucket_counts"].items():
        lines.append(f"{count:5}  {name}")

    lines.extend(["", "Största notationer per huvudgrupp:"])
    for bucket, counts in summary["notation_counts"].items():
        lines.append(f"  {bucket}:")
        for notation, count in counts.items():
            lines.append(f"    {count:5}  {notation or '(tomt)'}")

    lines.extend(["", "Största exakta grupper:"])
    for index, group in enumerate(summary["groups"][:80], start=1):
        examples = ", ".join(
            item["lemma"] + (f" ({item['homonym_number']})" if item["homonym_number"] else "")
            for item in group["examples"][:12]
        )
        lines.extend([
            "",
            f"{index}. {group['count']} | {group['bucket']} | {group['notation'] or '(tomt)'}",
            f"   SAOL-former som SALDO saknar: {', '.join(group['saol_only']) or '–'}",
            f"   SALDO-former som SAOL saknar: {', '.join(group['saldo_only']) or '–'}",
            f"   Exempel: {examples}",
        ])
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()
    summary = analyze(read_jsonl(args.input))
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render(summary), encoding="utf-8")
    args.json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Poster: {summary['records']}")
    for name, count in summary["bucket_counts"].items():
        print(f"{name}: {count}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
