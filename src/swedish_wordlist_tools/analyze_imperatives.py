from __future__ import annotations

import argparse
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .jsonl import read_jsonl
from .verb_game_fallback import interpret_playable_verb_slots

DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_SALDO = Path("data/raw/saldom.xml")
DEFAULT_TEXT = Path("reports/saol14-imperatives.txt")
DEFAULT_JSON = Path("reports/saol14-imperatives.json")

_IMPERATIVE_SEGMENT_RE = re.compile(r"\bimper\.\s*(?P<body>[^,;_]*)", re.IGNORECASE)
_FORM_RE = re.compile(r"[+\-]?[A-Za-zÅÄÖåäöÉéÜü]+(?:-[A-Za-zÅÄÖåäöÉéÜü]+)*")
_MARKER_WORDS = {"el", "eller", "vard", "åld", "prov", "ibl", "och", "obrukl"}
_FORM_CONTAINER_NAMES = {"wordform", "form", "formrepresentation"}
_WRITTEN_FORM_NAMES = {"writtenform", "written-form", "orthography"}
_MSD_NAMES = {
    "msd",
    "msdtag",
    "morphosyntacticdescription",
    "morphosyntacticlabel",
    "grammaticalinformation",
    "grammaticalfeatures",
    "paradigmslot",
    "slot",
}
_IMPERATIVE_LABEL_RE = re.compile(
    r"(?:^|[._+\-:/\s])(?:imp|imper|imperativ|imperative)(?:$|[._+\-:/\s])",
    re.IGNORECASE,
)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _normalise(value: str) -> str:
    return unicodedata.normalize("NFC", value.strip())


def _feature_values(element: ET.Element, names: set[str]) -> list[str]:
    wanted = {name.casefold() for name in names}
    values: list[str] = []
    for node in element.iter():
        local = _local_name(node.tag).casefold()
        if local in wanted and node.text:
            values.append(_normalise(node.text))
        for attribute, value in node.attrib.items():
            attr = _local_name(attribute).casefold()
            if attr in wanted:
                values.append(_normalise(value))
            elif attr in {"att", "name", "type"} and value.casefold() in wanted:
                feature_value = node.attrib.get("val") or node.attrib.get("value")
                if feature_value:
                    values.append(_normalise(feature_value))
    return [value for value in values if value]


def _first_word(lemma: str) -> str:
    return lemma.partition(" ")[0]


def _preterite_forms(slots: Any) -> tuple[str, ...]:
    if slots is None:
        return ()
    return tuple(form.partition(" ")[0] for form in slots.forms_for("preterite"))


def generate_imperative(lemma: str, slots: Any) -> tuple[str | None, str]:
    """Generate one conservative imperative candidate and name the rule."""
    if " " in lemma.strip():
        return None, "multiword_lemma"
    word = _first_word(lemma).casefold()
    if not word or not word.isalpha():
        return None, "not_single_alpha_head"
    if not word.endswith("a"):
        return word, "non_a_infinitive"
    preterites = _preterite_forms(slots)
    if any(form.casefold().endswith("ade") for form in preterites):
        return word, "class1_preterite_ade"
    if len(word) <= 2:
        return word, "short_a_infinitive"
    return word[:-1], "drop_final_a"


def _apply_explicit_token(lemma: str, token: str) -> str | None:
    head = _first_word(lemma).casefold()
    token = token.casefold()
    if token.startswith("+"):
        return head + token[1:]
    if token.startswith("-"):
        suffix = token[1:]
        if not suffix:
            return None
        for start in range(len(head)):
            if head[start:].startswith(suffix[:1]):
                return head[:start] + suffix
        return None
    return token


def explicit_saol_imperatives(record: dict[str, Any]) -> tuple[str, ...]:
    text = str(record.get("text") or "")
    match = _IMPERATIVE_SEGMENT_RE.search(text)
    if match is None:
        return ()
    body = match.group("body").strip()
    lemma = str(record.get("normaliserat_ord") or "").strip()
    tokens = _FORM_RE.findall(body)
    if len(text) == 50 and match.end() == len(text) and body and body[-1].isalpha():
        # The final token may be cut by the source hard cap. Earlier complete
        # alternatives in the same segment are still usable.
        tokens = tokens[:-1]
    result: list[str] = []
    for token in tokens:
        if token.casefold().lstrip("+-") in _MARKER_WORDS:
            continue
        written = _apply_explicit_token(lemma, token)
        if written and written.isalpha() and written not in result:
            result.append(written)
    return tuple(result)


def _is_imperative_label(label: str) -> bool:
    return _IMPERATIVE_LABEL_RE.search(label.casefold()) is not None


def read_saldo_form_labels(
    path: Path,
) -> tuple[dict[str, dict[str, set[str]]], Counter[str]]:
    """Read SALDO forms and their raw MSD/slot labels, grouped by lemma.

    The SALDO exports used by the project are LMF-like but may spell the label
    feature differently. We therefore recognise several standard feature names
    and retain the raw values in the report. An empty label set means that the
    form exists but no supported form label was exposed by the XML structure.
    """
    entries: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    observed_labels: Counter[str] = Counter()

    for _, element in ET.iterparse(path, events=("end",)):
        if _local_name(element.tag).casefold() != "lexicalentry":
            continue

        lemma_forms: list[str] = []
        for child in element:
            if _local_name(child.tag).casefold() == "lemma":
                lemma_forms.extend(_feature_values(child, _WRITTEN_FORM_NAMES))
        lemma_keys = {_normalise(lemma).casefold() for lemma in lemma_forms if lemma}
        if not lemma_keys:
            element.clear()
            continue

        found_container = False
        for node in element.iter():
            if _local_name(node.tag).casefold() not in _FORM_CONTAINER_NAMES:
                continue
            forms = _feature_values(node, _WRITTEN_FORM_NAMES)
            if not forms:
                continue
            found_container = True
            labels = set(_feature_values(node, _MSD_NAMES))
            for label in labels:
                observed_labels[label] += 1
            for lemma_key in lemma_keys:
                for form in forms:
                    entries[lemma_key][_normalise(form).casefold()].update(labels)

        # Some LMF files place FormRepresentation directly under WordForm; the
        # recursive feature reader above handles that. This fallback only keeps
        # form presence if the export has no recognised form containers.
        if not found_container:
            all_forms = _feature_values(element, _WRITTEN_FORM_NAMES)
            for lemma_key in lemma_keys:
                for form in all_forms:
                    entries[lemma_key][_normalise(form).casefold()]
        element.clear()

    return (
        {lemma: {form: set(labels) for form, labels in forms.items()} for lemma, forms in entries.items()},
        observed_labels,
    )


def build_report(saol_path: Path = DEFAULT_SAOL, saldo_path: Path = DEFAULT_SALDO) -> dict[str, Any]:
    saldo, observed_labels = read_saldo_form_labels(saldo_path)
    rows: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    rule_counts: Counter[str] = Counter()

    for record in read_jsonl(saol_path):
        if str(record.get("upos", "")).upper() != "VERB":
            continue
        lemma = str(record.get("normaliserat_ord") or "").strip()
        playable = interpret_playable_verb_slots(record)
        candidate, rule = generate_imperative(lemma, playable)
        explicit = explicit_saol_imperatives(record)
        saldo_forms = saldo.get(lemma.casefold(), {})
        candidate_labels = saldo_forms.get(candidate or "", set())
        rule_counts[rule] += 1

        if candidate is None:
            status = "not_generated"
        elif candidate not in saldo_forms:
            status = "generated_missing_from_exact_saldo_lemma"
        elif any(_is_imperative_label(label) for label in candidate_labels):
            status = "generated_as_imperative_in_saldo"
        elif candidate_labels:
            status = "generated_in_saldo_but_not_labelled_imperative"
        else:
            status = "generated_in_saldo_without_readable_msd"
        counts[status] += 1

        explicit_status = "none"
        if explicit:
            explicit_status = (
                "generated_matches_explicit_saol"
                if candidate in explicit
                else "generated_differs_from_explicit_saol"
            )
            counts[explicit_status] += 1

        rows.append(
            {
                "lemma": lemma,
                "homonr": str(record.get("homonr") or ""),
                "rule": rule,
                "generated": candidate,
                "status": status,
                "explicit_saol": list(explicit),
                "explicit_status": explicit_status,
                "saldo_candidate_labels": sorted(candidate_labels),
                "saldo_candidate_is_imperative": any(
                    _is_imperative_label(label) for label in candidate_labels
                ),
                "saldo_forms_sample": sorted(saldo_forms)[:30],
                "text": str(record.get("text") or ""),
            }
        )

    rows.sort(
        key=lambda row: (
            row["status"],
            row["explicit_status"],
            row["lemma"],
            row["homonr"],
        )
    )
    generated = sum(1 for row in rows if row["generated"])
    imperative_confirmed = counts["generated_as_imperative_in_saldo"]
    exact_form_matches = sum(
        counts[key]
        for key in (
            "generated_as_imperative_in_saldo",
            "generated_in_saldo_but_not_labelled_imperative",
            "generated_in_saldo_without_readable_msd",
        )
    )
    exact_labelled_matches = (
        counts["generated_as_imperative_in_saldo"]
        + counts["generated_in_saldo_but_not_labelled_imperative"]
    )
    return {
        "verb_records": len(rows),
        "generated_candidates": generated,
        "generated_form_found_in_saldo": exact_form_matches,
        "generated_as_imperative_in_saldo": imperative_confirmed,
        "generated_as_imperative_percent_of_generated": round(
            100 * imperative_confirmed / generated, 2
        ) if generated else 0.0,
        "generated_as_imperative_percent_of_labelled_matches": round(
            100 * imperative_confirmed / exact_labelled_matches, 2
        ) if exact_labelled_matches else 0.0,
        "explicit_saol_records": sum(1 for row in rows if row["explicit_saol"]),
        "status_counts": dict(counts.most_common()),
        "rule_counts": dict(rule_counts.most_common()),
        "observed_saldo_msd_labels": dict(observed_labels.most_common()),
        "imperative_saldo_msd_labels": {
            label: count
            for label, count in observed_labels.most_common()
            if _is_imperative_label(label)
        },
        "records": rows,
        "note": (
            "SALDO is validation only. A candidate is confirmed only when the "
            "same form has an imperative-like MSD/slot label; absence from SALDO "
            "does not reject a SAOL-derived candidate."
        ),
    }


def render_text(report: dict[str, Any]) -> str:
    lines = [
        f"Verbposter: {report['verb_records']}",
        f"Genererade imperativkandidater: {report['generated_candidates']}",
        f"Kandidatformen finns hos exakt SALDO-lemma: {report['generated_form_found_in_saldo']}",
        f"Bekräftade som imperativ av SALDO-MSD: {report['generated_as_imperative_in_saldo']} "
        f"({report['generated_as_imperative_percent_of_generated']:.2f} % av alla genererade; "
        f"{report['generated_as_imperative_percent_of_labelled_matches']:.2f} % av etiketterade formträffar)",
        f"Poster med uttryckligt SAOL-imperativ: {report['explicit_saol_records']}",
        "",
        "Status:",
    ]
    for key, count in report["status_counts"].items():
        lines.append(f"  {count:6d}  {key}")
    lines.extend(["", "Regler:"])
    for key, count in report["rule_counts"].items():
        lines.append(f"  {count:6d}  {key}")
    lines.extend(["", "SALDO-etiketter som känns igen som imperativ:"])
    for label, count in report["imperative_saldo_msd_labels"].items():
        lines.append(f"  {count:6d}  {label}")
    if not report["imperative_saldo_msd_labels"]:
        lines.append("  (inga; kontrollera listan över observerade MSD-värden i JSON-rapporten)")

    def section(title: str, status: str, limit: int = 100) -> None:
        lines.extend(["", title + ":"])
        selected = [
            row
            for row in report["records"]
            if row.get("explicit_status") == status or row.get("status") == status
        ][:limit]
        for row in selected:
            lines.append(
                f"  {row['lemma']} (homonr={row['homonr']}) -> {row['generated']} "
                f"| rule={row['rule']} | status={row['status']} "
                f"| saldo_msd={row['saldo_candidate_labels']} "
                f"| explicit={row['explicit_saol']}"
            )
        if not selected:
            lines.append("  (inga)")

    section(
        "Avviker från uttryckligt SAOL-imperativ",
        "generated_differs_from_explicit_saol",
    )
    section(
        "Finns i SALDO men saknar imperativetikett",
        "generated_in_saldo_but_not_labelled_imperative",
    )
    section(
        "Finns i SALDO men MSD kunde inte läsas",
        "generated_in_saldo_without_readable_msd",
    )
    section(
        "Saknas hos exakt matchat SALDO-lemma",
        "generated_missing_from_exact_saldo_lemma",
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit generated SAOL14 imperatives against SALDO MSD labels"
    )
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("saldo", nargs="?", type=Path, default=DEFAULT_SALDO)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()
    report = build_report(args.saol, args.saldo)
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render_text(report), encoding="utf-8")
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Verbposter: {report['verb_records']}")
    print(f"Genererade kandidater: {report['generated_candidates']}")
    print(
        "Bekräftade som imperativ av SALDO-MSD: "
        f"{report['generated_as_imperative_in_saldo']} "
        f"({report['generated_as_imperative_percent_of_generated']:.2f} %)"
    )
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
