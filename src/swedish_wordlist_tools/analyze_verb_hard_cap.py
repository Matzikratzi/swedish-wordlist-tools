from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from .export_verb_forms import build_verb_forms
from .jsonl import read_jsonl
from .verb_game_fallback import interpret_playable_verb_slots
from .verb_slots import interpret_verb_slots

DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_TEXT = Path("reports/saol14-verb-hard-cap.txt")
DEFAULT_JSON = Path("reports/saol14-verb-hard-cap.json")
TEXT_HARD_CAP = 50
_LABEL_RE = re.compile(r"\b(pres|pret|sup|imper|inf)\.\s*", re.IGNORECASE)
_BARE_FINAL_LABEL_RE = re.compile(r"\b(pres|pret|sup|imper|inf)\.\s*$", re.IGNORECASE)
_WORD_RE = re.compile(r"[A-Za-zÅÄÖåäöÉéÜü-]+$")


def _last_label(text: str) -> str:
    matches = list(_LABEL_RE.finditer(text))
    return matches[-1].group(1).casefold() if matches else "unlabelled"


def _tail_kind(text: str) -> str:
    """Describe how the 50-character field ends without guessing a form."""
    if not text:
        return "empty"
    if _BARE_FINAL_LABEL_RE.search(text):
        return "label"
    if text[-1] in ",;:.()[]":
        return "delimiter"
    match = _WORD_RE.search(text)
    if match is None:
        return "other"
    return "word_fragment_or_complete_word"


def _missing_share(exported: int, estimated_missing: int) -> float:
    total = exported + estimated_missing
    return round(100 * estimated_missing / total, 2) if total else 0.0


def _estimate_scenarios(exported: int, candidates: int) -> dict[str, dict[str, Any]]:
    """Show transparent assumptions instead of pretending to know hidden text."""
    result: dict[str, dict[str, Any]] = {}
    for per_record in (1, 2, 3):
        missing = candidates * per_record
        result[f"{per_record}_missing_per_candidate"] = {
            "assumed_missing_forms_per_candidate": per_record,
            "estimated_missing_form_occurrences": missing,
            "estimated_missing_share_percent": _missing_share(exported, missing),
        }
    return result


def build_report(saol_path: Path = DEFAULT_SAOL) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    label_counts: Counter[str] = Counter()
    tail_counts: Counter[str] = Counter()
    strict_counts: Counter[str] = Counter()
    verb_records = 0

    for record in read_jsonl(saol_path):
        if str(record.get("upos", "")).upper() != "VERB":
            continue
        verb_records += 1
        text = str(record.get("text") or "")
        if len(text) != TEXT_HARD_CAP:
            continue

        strict = interpret_verb_slots(record)
        playable = interpret_playable_verb_slots(record)
        label = _last_label(text)
        tail = _tail_kind(text)
        label_counts[label] += 1
        tail_counts[tail] += 1
        strict_counts[
            "strict_interpreted" if strict is not None else "strict_uninterpreted"
        ] += 1

        strict_forms = list(strict.written_forms()) if strict is not None else []
        playable_forms = list(playable.written_forms()) if playable is not None else []
        records.append(
            {
                "lemma": str(record.get("normaliserat_ord") or ""),
                "homonr": str(record.get("homonr") or ""),
                "text": text,
                "last_label": label,
                "tail_kind": tail,
                "strict_forms": strict_forms,
                "playable_forms": playable_forms,
                "possible_missing_after_cap": tail != "delimiter",
                "source": str(record.get("source") or ""),
            }
        )

    records.sort(key=lambda row: (row["last_label"], row["lemma"], row["homonr"]))
    candidates = sum(1 for row in records if row["possible_missing_after_cap"])
    exported_words, _export_report = build_verb_forms(saol_path)
    exported_count = len(exported_words)
    return {
        "hard_cap": TEXT_HARD_CAP,
        "verb_records": verb_records,
        "records_at_hard_cap": len(records),
        "records_at_hard_cap_percent": round(100 * len(records) / verb_records, 2)
        if verb_records
        else 0.0,
        "strict_status": dict(strict_counts.most_common()),
        "last_label_counts": dict(label_counts.most_common()),
        "tail_kind_counts": dict(tail_counts.most_common()),
        "possible_missing_after_cap": candidates,
        "possible_missing_after_cap_percent_of_verbs": round(
            100 * candidates / verb_records, 2
        )
        if verb_records
        else 0.0,
        "exported_unique_playable_verb_forms": exported_count,
        "missing_form_estimates": _estimate_scenarios(exported_count, candidates),
        "records": records,
        "note": (
            "possible_missing_after_cap is a review flag only. A bare final "
            "grammatical label such as 'pres.' or 'inf.' is open even though it "
            "ends in a period. The report never invents text beyond character 50."
        ),
    }


def render_text(report: dict[str, Any]) -> str:
    lines = [
        f"Verbposter totalt: {report['verb_records']}",
        f"Verbposter med text exakt {report['hard_cap']} tecken: "
        f"{report['records_at_hard_cap']} "
        f"({report['records_at_hard_cap_percent']:.2f} %)",
        f"Kontrollkandidater efter kapningen: {report['possible_missing_after_cap']} "
        f"({report['possible_missing_after_cap_percent_of_verbs']:.2f} % av verbposterna)",
        f"Exporterade unika spelbara verbformer: "
        f"{report['exported_unique_playable_verb_forms']}",
        "",
        "Rimlighetsintervall för saknade former:",
    ]
    for scenario in report["missing_form_estimates"].values():
        lines.append(
            "  om varje kontrollkandidat döljer "
            f"{scenario['assumed_missing_forms_per_candidate']} form(er): "
            f"cirka {scenario['estimated_missing_form_occurrences']} formförekomster, "
            f"motsvarande ungefär "
            f"{scenario['estimated_missing_share_percent']:.2f} % av den tänkta "
            "SAOL14-formmängden"
        )

    lines.extend(["", "Strikt tolkning:"])
    for key, count in report["strict_status"].items():
        lines.append(f"  {count:5d}  {key}")
    lines.extend(["", "Sista grammatiska markör:"])
    for key, count in report["last_label_counts"].items():
        lines.append(f"  {count:5d}  {key}")
    lines.extend(["", "Fältslut:"])
    for key, count in report["tail_kind_counts"].items():
        lines.append(f"  {count:5d}  {key}")
    lines.extend(["", "Poster:"])
    for row in report["records"]:
        flag = "review" if row["possible_missing_after_cap"] else "closed"
        lines.append(
            f"  {row['lemma']} (homonr={row['homonr']}) | {flag} | "
            f"last={row['last_label']} | tail={row['tail_kind']} | "
            f"strict={row['strict_forms']} | playable={row['playable_forms']} | "
            f"text={row['text']!r}"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit SAOL14 verb rows that hit the observed 50-character text cap"
    )
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()

    report = build_report(args.saol)
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render_text(report), encoding="utf-8")
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Verbposter vid 50 tecken: {report['records_at_hard_cap']}")
    print(f"Kontrollkandidater: {report['possible_missing_after_cap']}")
    print(
        "Uppskattad saknad andel vid 1 form/kandidat: "
        f"{report['missing_form_estimates']['1_missing_per_candidate']['estimated_missing_share_percent']:.2f} %"
    )
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
