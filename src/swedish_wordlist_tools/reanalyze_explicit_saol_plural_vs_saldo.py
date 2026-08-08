from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

DEFAULT_INPUT = Path("reports/saol14-direct-form-validation.jsonl")
DEFAULT_TEXT = Path("reports/saol14-explicit-plural-vs-saldo-reanalysis.txt")
DEFAULT_JSON = Path("reports/saol14-explicit-plural-vs-saldo-reanalysis.json")

# The purpose of this audit is deliberately semantic and independent of the old
# mismatch classes: if the article text explicitly licenses a plural slot, we
# inspect generated SAOL forms that SALDO lacks.
_EXPLICIT_PLURAL_RE = re.compile(
    r"(?:^|[;,_ ]|\bpl\.\s*)"
    r"(?:\+(?:ar|er|or|r|n|s)|pl\.\s*\+|pl\.\s*[^;,_ ]+)",
    re.IGNORECASE,
)

PLURAL_SUFFIXES = (
    "ar", "ars", "arna", "arnas",
    "er", "ers", "erna", "ernas",
    "or", "ors", "orna", "ornas",
    "r", "rs", "rna", "rnas",
    "n", "ns", "na", "nas",
)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def has_explicit_plural(notation: str) -> bool:
    value = notation.strip()
    if not value:
        return False
    # Common compact noun patterns put the plural directly after definite
    # singular, e.g. +en +er, +en +ar, +t +n, +n +r.
    tokens = value.replace(";", " ").replace(",", " ").split()
    plus_tokens = [token for token in tokens if token.startswith("+")]
    if len(plus_tokens) >= 2:
        return True
    if "pl." in value.casefold():
        return True
    return bool(_EXPLICIT_PLURAL_RE.search(value))


def _relative(lemma: str, form: object) -> str:
    word = str(form).casefold()
    base = lemma.casefold()
    if base and word.startswith(base):
        return "+" + word[len(base):]
    return "=" + word


def _looks_plural_relative(relative: str) -> bool:
    if not relative.startswith("+"):
        return False
    suffix = relative[1:]
    return suffix in PLURAL_SUFFIXES


def candidates(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in rows:
        if str(row.get("upos") or "").upper() != "NOUN":
            continue
        notation = str(row.get("notation") or "").strip()
        if not has_explicit_plural(notation):
            continue
        lemma = str(row.get("lemma") or "")
        extra = [str(value) for value in row.get("extra_from_saol", ())]
        if not extra:
            continue
        relative = sorted(_relative(lemma, value) for value in extra)
        plural_extra = [value for value in relative if _looks_plural_relative(value)]
        if not plural_extra:
            continue
        result.append({
            "lemma": lemma,
            "homonym_number": str(row.get("homonym_number") or ""),
            "record_id": str(row.get("record_id") or ""),
            "notation": notation,
            "status": str(row.get("status") or ""),
            "semantic_status": str(row.get("semantic_status") or ""),
            "match_method": str(row.get("match_method") or ""),
            "extra_from_saol": extra,
            "extra_relative": relative,
            "plural_extra_relative": plural_extra,
            "missing_from_saol": list(row.get("missing_from_saol", ())),
        })
    result.sort(key=lambda item: (item["notation"], item["lemma"].casefold(), item["homonym_number"]))
    return result


def build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    notation_counts = Counter(row["notation"] for row in rows)
    status_counts = Counter(row["status"] for row in rows)
    semantic_counts = Counter(row["semantic_status"] for row in rows)
    groups: dict[tuple[str, tuple[str, ...], tuple[str, ...]], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(
            row["notation"],
            tuple(row["plural_extra_relative"]),
            tuple(sorted(_relative(row["lemma"], value) for value in row["missing_from_saol"])),
        )].append(row)
    ordered = sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))
    return {
        "records": len(rows),
        "status_counts": dict(status_counts.most_common()),
        "semantic_status_counts": dict(semantic_counts.most_common()),
        "notation_counts": dict(notation_counts.most_common()),
        "groups": [
            {
                "notation": key[0],
                "saol_plural_extra": list(key[1]),
                "saldo_only": list(key[2]),
                "count": len(members),
                "examples": [
                    {"lemma": row["lemma"], "homonym_number": row["homonym_number"]}
                    for row in members[:15]
                ],
            }
            for key, members in ordered
        ],
        "rows": rows,
    }


def render(summary: dict[str, Any]) -> str:
    lines = [
        "SAOL14 omstart: explicit plural i artikeltext vs SALDO",
        "",
        "Urvalet använder INTE gamla mismatch-klasser.",
        "Krav: NOUN, artikeln licensierar plural explicit, och SAOL-generatorn har",
        "minst en pluralform som SALDO saknar.",
        "",
        f"Poster: {summary['records']}",
        "",
        "Nuvarande valideringsstatus:",
    ]
    for name, count in summary["status_counts"].items():
        lines.append(f"{count:5}  {name or '(tomt)'}")
    lines.extend(["", "Semantisk status:"])
    for name, count in summary["semantic_status_counts"].items():
        lines.append(f"{count:5}  {name or '(tomt)'}")
    lines.extend(["", "Största notationer:"])
    for name, count in list(summary["notation_counts"].items())[:30]:
        lines.append(f"{count:5}  {name}")
    lines.extend(["", "Största exakta grupper:"])
    for index, group in enumerate(summary["groups"][:60], start=1):
        examples = ", ".join(
            item["lemma"] + (f" ({item['homonym_number']})" if item["homonym_number"] else "")
            for item in group["examples"]
        )
        lines.extend([
            "",
            f"{index}. {group['count']} | {group['notation']}",
            f"   SAOL-plural som SALDO saknar: {', '.join(group['saol_plural_extra'])}",
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
