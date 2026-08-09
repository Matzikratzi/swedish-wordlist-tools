from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .noun_mechanical_validation import is_mechanically_verified_noun_row

DEFAULT_INPUT = Path("reports/saol14-direct-form-validation.jsonl")
DEFAULT_TEXT = Path("reports/saol14-remaining-noun-notations.txt")
DEFAULT_JSON = Path("reports/saol14-remaining-noun-notations.json")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _relative(lemma: str, form: object) -> str:
    word = str(form)
    base = lemma
    if base and word.casefold().startswith(base.casefold()):
        return "+" + word[len(base):]
    return "=" + word


def candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        if str(row.get("upos") or "").upper() != "NOUN":
            continue
        if str(row.get("status") or "") != "form_set_mismatch":
            continue
        if is_mechanically_verified_noun_row(row):
            continue
        lemma = str(row.get("lemma") or "")
        generated = [str(v) for v in row.get("generated_forms", ())]
        saldo = [str(v) for v in row.get("saldo_forms", ())]
        result.append({
            "lemma": lemma,
            "homonym_number": str(row.get("homonym_number") or ""),
            "record_id": str(row.get("record_id") or ""),
            "notation": str(row.get("notation") or "").strip(),
            "ordkl": str(row.get("ordkl") or ""),
            "match_method": str(row.get("match_method") or ""),
            "generated_forms": generated,
            "saldo_forms": saldo,
            "saol_only": sorted(set(generated) - set(saldo)),
            "saldo_only": sorted(set(saldo) - set(generated)),
            "saol_only_relative": sorted(_relative(lemma, v) for v in set(generated) - set(saldo)),
            "saldo_only_relative": sorted(_relative(lemma, v) for v in set(saldo) - set(generated)),
        })
    return result


def build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row["notation"]].append(row)
    ordered = sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))
    return {
        "records": len(rows),
        "notation_groups": len(groups),
        "groups": [
            {
                "notation": notation,
                "count": len(members),
                "match_methods": dict(Counter(m["match_method"] for m in members).most_common()),
                "difference_patterns": [
                    {
                        "saol_only": list(key[0]), "saldo_only": list(key[1]), "count": len(pattern_members),
                        "examples": [{"lemma": m["lemma"], "homonym_number": m["homonym_number"], "record_id": m["record_id"]} for m in pattern_members[:12]],
                    }
                    for key, pattern_members in sorted(
                        defaultdict(list, {
                            key: [m for m in members if (tuple(m["saol_only_relative"]), tuple(m["saldo_only_relative"])) == key]
                            for key in {(tuple(m["saol_only_relative"]), tuple(m["saldo_only_relative"])) for m in members}
                        }).items(), key=lambda item: (-len(item[1]), item[0])
                    )[:8]
                ],
                "examples": [{"lemma": m["lemma"], "homonym_number": m["homonym_number"], "record_id": m["record_id"], "generated_forms": m["generated_forms"], "saldo_forms": m["saldo_forms"]} for m in members[:20]],
            }
            for notation, members in ordered
        ],
    }


def render(summary: dict[str, Any]) -> str:
    lines = [
        "SAOL14 NOUN: kvarvarande mismatch grupperade efter rå notation", "",
        "Mekaniskt verifierade SAOL-paradigm är bortfiltrerade, oavsett om", "informationen kommer från text eller ordkl. SALDO visas endast som", "diagnostik för den återstående kön.", "",
        f"Poster: {summary['records']}", f"Notationer: {summary['notation_groups']}", "", "Största notationer:",
    ]
    for index, group in enumerate(summary["groups"][:80], start=1):
        notation = group["notation"] or "(tom notation)"
        lines.extend(["", f"{index}. {group['count']} | {notation}"])
        if group["match_methods"]:
            lines.append("   Matchmetoder: " + ", ".join(f"{k or '(tomt)'}={v}" for k, v in group["match_methods"].items()))
        for pattern in group["difference_patterns"][:4]:
            examples = ", ".join(item["lemma"] + (f" ({item['homonym_number']})" if item["homonym_number"] else "") for item in pattern["examples"][:8])
            lines.append(f"   {pattern['count']}× SAOL-only={pattern['saol_only'] or ['–']} | SALDO-only={pattern['saldo_only'] or ['–']} | {examples}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()
    summary = build_summary(candidates(read_jsonl(args.input)))
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render(summary), encoding="utf-8")
    args.json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Poster: {summary['records']}")
    print(f"Notationer: {summary['notation_groups']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
