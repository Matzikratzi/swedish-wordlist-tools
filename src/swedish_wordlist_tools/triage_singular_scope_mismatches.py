from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .analyze_singular_agreement_for_scope_extras import candidates as scope_candidates

DEFAULT_INPUT = Path("reports/saol14-direct-form-validation.jsonl")
DEFAULT_TEXT = Path("reports/saol14-singular-scope-mismatch-triage.txt")
DEFAULT_JSON = Path("reports/saol14-singular-scope-mismatch-triage.json")

VARIANT_ORTHOGRAPHY = "variant_or_orthography"
COMPETING_DEFINITE_SINGULAR = "competing_definite_singular"
MULTIWORD_OR_TOKENIZATION = "multiword_or_tokenization"
OTHER = "other_singular_mismatch"

DEFINITE_PAIRS = {
    frozenset(("+en", "+ens")),
    frozenset(("+et", "+ets")),
    frozenset(("+n", "+ns")),
    frozenset(("+t", "+ts")),
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _is_multiword(lemma: str) -> bool:
    return any(char.isspace() for char in lemma) or "- och " in lemma.casefold()


def classify(row: dict[str, Any]) -> tuple[str, str]:
    lemma = str(row.get("lemma") or "")
    missing = set(row.get("missing_singular_relative", ()))
    saldo_extra = set(row.get("saldo_extra_relative", ()))

    if _is_multiword(lemma):
        return MULTIWORD_OR_TOKENIZATION, "lemma is multiword/coordination; SALDO extras suggest tokenized or phrase-level matching"

    # Forms that no longer share the SAOL lemma prefix are strong evidence that
    # we are looking at an orthographic/lexical variant or a different lemma
    # realization rather than a simple inflection-slot disagreement.
    if any(value.startswith("=") for value in missing | saldo_extra):
        return VARIANT_ORTHOGRAPHY, "at least one differing form is not a suffix operation on the SAOL lemma"

    if frozenset(missing) in DEFINITE_PAIRS:
        competing_pairs = [pair for pair in DEFINITE_PAIRS if pair.issubset(saldo_extra)]
        if competing_pairs:
            return COMPETING_DEFINITE_SINGULAR, "SAOL singular definite pair is absent while SALDO supplies a competing definite-singular pair"

    return OTHER, "singular disagreement is not explained by a spelling/variant form, multiword tokenization, or one competing definite-singular pair"


def triage(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in scope_candidates(rows):
        if row.get("singular_status") != "singular_mismatch":
            continue
        category, rationale = classify(row)
        result.append({**row, "triage": category, "triage_rationale": rationale})
    result.sort(key=lambda row: (row["triage"], row["notation"], row["lemma"].casefold(), row["homonym_number"]))
    return result


def build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["triage"] for row in rows)
    groups: dict[tuple[str, str, tuple[str, ...], tuple[str, ...]], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(
            row["triage"],
            row["notation"],
            tuple(row["missing_singular_relative"]),
            tuple(row["saldo_extra_relative"]),
        )].append(row)
    ordered = sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))
    return {
        "records": len(rows),
        "triage_counts": dict(counts.most_common()),
        "groups": [
            {
                "triage": key[0],
                "notation": key[1],
                "missing_singular": list(key[2]),
                "saldo_extra": list(key[3]),
                "count": len(members),
                "examples": [
                    {
                        "lemma": row["lemma"],
                        "homonym_number": row["homonym_number"],
                        "match_method": row.get("match_method", ""),
                    }
                    for row in members[:20]
                ],
            }
            for key, members in ordered
        ],
        "rows": rows,
    }


def render(summary: dict[str, Any]) -> str:
    lines = [
        "SAOL14 omstart: triage av singularmismatchar vid SALDO-extra utanför artikelomfång",
        "",
        f"Poster: {summary['records']}",
        "",
        "Triage:",
    ]
    for name, count in summary["triage_counts"].items():
        lines.append(f"{count:5}  {name}")
    lines.extend(["", "Största exakta grupper:"])
    for index, group in enumerate(summary["groups"][:60], start=1):
        examples = ", ".join(
            item["lemma"] + (f" ({item['homonym_number']})" if item["homonym_number"] else "")
            for item in group["examples"][:12]
        )
        lines.extend([
            "",
            f"{index}. {group['count']} | {group['triage']} | {group['notation']}",
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
    rows = triage(read_jsonl(args.input))
    summary = build_summary(rows)
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render(summary), encoding="utf-8")
    args.json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Poster: {summary['records']}")
    for name, count in summary["triage_counts"].items():
        print(f"{name}: {count}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
