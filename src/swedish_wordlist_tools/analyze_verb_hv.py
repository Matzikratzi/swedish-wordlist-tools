from __future__ import annotations

import argparse
import html
import json
import re
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from .jsonl import read_jsonl
from .verb_compound_heads import borrow_compound_verb_slots, build_simple_verb_paradigm_index
from .verb_game_fallback import interpret_playable_verb_slots
from .verb_slot_schema import add_explicit_verb_row_slots

DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_TEXT = Path("reports/saol14-verb-hv.txt")
DEFAULT_JSON = Path("reports/saol14-verb-hv.json")
_SUP_RE = re.compile(r"<sup\b[^>]*>.*?</sup>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")

_SUBJUNCTIVE_FORMS = {
    "bekomme", "finge", "ginge", "leve", "måtte", "torde",
    "vare", "varde", "vore",
}
_NONVERBAL_REFERENCE_FORMS = {"närmare", "närmre", "närmast", "närmst", "summarum"}
_OTHER_HISTORIC_FORMS = {
    "andre", "bevare", "bre", "ene", "färst", "göre", "rå",
    "talte", "talt", "förtalde", "förtalt",
}
_HISTORIC_INFINITIVE_ENDINGS = (
    "giva", "givas", "taga", "tagas", "draga", "dragas", "bliva",
    "bedja", "kläda", "späda",
)
_INFLECTION_ENDINGS = (
    "ade", "at", "ats", "de", "des", "dde", "ddes", "er", "es",
    "it", "its", "s", "te", "tes", "t",
)
_CLASSIFICATION_ORDER = (
    "subjunctive",
    "historic_infinitive",
    "alternative_spelling",
    "nonverbal_reference",
    "other_historic_reference",
    "possible_inflection",
    "unclassified",
)


def _plain(value: object) -> str:
    text = html.unescape(str(value or ""))
    text = _SUP_RE.sub("", text)
    text = _TAG_RE.sub("", text)
    return text.replace("·", "").strip().casefold()


def _verb_form_index(records: list[dict[str, Any]]) -> dict[str, set[str]]:
    verbs = [record for record in records if str(record.get("upos", "")).upper() == "VERB"]
    interpreted = {
        id(record): (
            add_explicit_verb_row_slots(record, slots)
            if (slots := interpret_playable_verb_slots(record)) is not None
            else None
        )
        for record in verbs
    }
    head_index = build_simple_verb_paradigm_index(verbs, interpreted)
    result: dict[str, set[str]] = defaultdict(set)
    for record in verbs:
        lemma = _plain(record.get("normaliserat_ord"))
        slots = borrow_compound_verb_slots(record, head_index, interpreted[id(record)])
        if not lemma or slots is None:
            continue
        for form in slots.written_forms():
            written = _plain(form)
            if written:
                result[lemma].add(written)
    return dict(result)


def _common_prefix_length(left: str, right: str) -> int:
    length = 0
    for a, b in zip(left, right):
        if a != b:
            break
        length += 1
    return length


def _looks_like_infinitive(form: str) -> bool:
    return len(form) >= 3 and form.endswith(("a", "as"))


def _is_historic_infinitive(form: str) -> bool:
    return form.endswith(_HISTORIC_INFINITIVE_ENDINGS)


def _is_alternative_spelling(form: str, target: str) -> bool:
    if not _looks_like_infinitive(form):
        return False
    if not (target.endswith(("a", "as", "e", "i", "ä")) or len(target) <= 3):
        return False
    return SequenceMatcher(None, form, target).ratio() >= 0.45


def classify_missing_reference(form: str, target: str) -> tuple[str, str]:
    """Return a conservative review label for a missing SAOL (hv) form."""
    if form in _SUBJUNCTIVE_FORMS:
        return "subjunctive", "known_subjunctive_form"
    if form in _NONVERBAL_REFERENCE_FORMS:
        return "nonverbal_reference", "reference_is_not_a_verb_form_in_this_use"
    if _is_historic_infinitive(form):
        return "historic_infinitive", "historic_long_infinitive_pattern"
    if _is_alternative_spelling(form, target):
        return "alternative_spelling", "infinitive_like_reference_close_to_target"
    if form in _OTHER_HISTORIC_FORMS:
        return "other_historic_reference", "known_historic_or_formulaic_reference"

    shared = _common_prefix_length(form, target)
    if shared >= 3 and form.endswith(_INFLECTION_ENDINGS):
        return "possible_inflection", "shares_target_stem_and_inflectional_ending"
    return "unclassified", "no_conservative_rule_matched"


def build_report(saol_path: Path = DEFAULT_SAOL) -> dict[str, Any]:
    records = list(read_jsonl(saol_path))
    verb_forms = _verb_form_index(records)
    rows: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    class_counts: Counter[str] = Counter()

    for record in records:
        if str(record.get("ordkl") or "").strip().casefold() != "(hv)":
            continue
        target = _plain(record.get("normaliserat_ord"))
        referred_form = _plain(record.get("ord")) or _plain(record.get("stycke"))
        if target not in verb_forms:
            continue

        classification = "not_applicable"
        reason = ""
        if not referred_form or " " in referred_form or not referred_form.isalpha():
            status = "not_single_playable_form"
        elif referred_form in verb_forms[target]:
            status = "matched_generated_verb_form"
        else:
            status = "missing_from_generated_verb_forms"
            classification, reason = classify_missing_reference(referred_form, target)
            class_counts[classification] += 1
        counts[status] += 1
        rows.append({
            "form": referred_form,
            "target_lemma": target,
            "target_homonr": str(record.get("homonr") or ""),
            "status": status,
            "classification": classification,
            "classification_reason": reason,
            "generated_forms": sorted(verb_forms[target]),
            "ord": str(record.get("ord") or ""),
            "stycke": str(record.get("stycke") or ""),
            "source": str(record.get("source") or ""),
        })

    rows.sort(key=lambda row: (
        row["status"], row["classification"], row["target_lemma"], row["form"]
    ))
    matched = counts["matched_generated_verb_form"]
    comparable = matched + counts["missing_from_generated_verb_forms"]
    possible_parser_misses = class_counts["possible_inflection"] + class_counts["unclassified"]
    return {
        "verb_lemmas_with_forms": len(verb_forms),
        "verb_targeted_hv_records": len(rows),
        "single_form_comparable_hv_records": comparable,
        "matched_generated_verb_forms": matched,
        "coverage_percent": round(100 * matched / comparable, 2) if comparable else 0.0,
        "possible_parser_misses": possible_parser_misses,
        "possible_parser_miss_percent_of_comparable": (
            round(100 * possible_parser_misses / comparable, 2) if comparable else 0.0
        ),
        "status_counts": dict(counts.most_common()),
        "missing_classification_counts": dict(class_counts.most_common()),
        "records": rows,
        "note": (
            "Classifications are conservative review labels. Only possible_inflection and "
            "unclassified are counted as possible parser misses; no (hv) form is exported automatically."
        ),
    }


def render_text(report: dict[str, Any]) -> str:
    lines = [
        f"Verbuppslagsord med former: {report['verb_lemmas_with_forms']}",
        f"(hv)-poster som pekar på verb: {report['verb_targeted_hv_records']}",
        f"Jämförbara enordsformer: {report['single_form_comparable_hv_records']}",
        f"Återfunna bland genererade verbformer: {report['matched_generated_verb_forms']} "
        f"({report['coverage_percent']:.2f} %)",
        f"Möjliga parsermissar: {report['possible_parser_misses']} "
        f"({report['possible_parser_miss_percent_of_comparable']:.2f} % av jämförbara)",
        "",
        "Status:",
    ]
    for status, count in report["status_counts"].items():
        lines.append(f"  {count:6d}  {status}")

    lines.extend(["", "Klassificering av saknade hänvisningar:"])
    for classification in _CLASSIFICATION_ORDER:
        count = report["missing_classification_counts"].get(classification, 0)
        lines.append(f"  {count:6d}  {classification}")

    for classification in _CLASSIFICATION_ORDER:
        lines.extend(["", classification + ":"])
        selected = [
            row for row in report["records"]
            if row["status"] == "missing_from_generated_verb_forms"
            and row["classification"] == classification
        ]
        if not selected:
            lines.append("  (inga)")
        for row in selected[:200]:
            lines.append(
                f"  {row['form']} -> {row['target_lemma']} "
                f"| reason={row['classification_reason']} "
                f"| generated={row['generated_forms']}"
            )

    lines.extend(["", "Ej jämförbara som enskilt spelord:"])
    selected = [row for row in report["records"] if row["status"] == "not_single_playable_form"]
    if not selected:
        lines.append("  (inga)")
    for row in selected[:200]:
        lines.append(
            f"  {row['form']} -> {row['target_lemma']} | generated={row['generated_forms']}"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit and classify SAOL14 verb forms against internal (hv) references"
    )
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()

    report = build_report(args.saol)
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render_text(report), encoding="utf-8")
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"(hv)-poster som pekar på verb: {report['verb_targeted_hv_records']}")
    print(f"Återfunna former: {report['matched_generated_verb_forms']} ({report['coverage_percent']:.2f} %)")
    print(f"Möjliga parsermissar: {report['possible_parser_misses']}")
    for classification in _CLASSIFICATION_ORDER:
        print(f"{classification}: {report['missing_classification_counts'].get(classification, 0)}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
