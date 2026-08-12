from __future__ import annotations

import argparse
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from .inflect import generate_entry
from .jsonl import read_jsonl

DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_SALDO = Path("data/raw/saldo.xml")
DEFAULT_TARGET = Path("data/processed/saol14-saldo-forms.txt")
DEFAULT_SAOL_ONLY = Path("reports/saol14-only.jsonl")
DEFAULT_AMBIGUOUS = Path("reports/saol14-saldo-ambiguous.jsonl")
DEFAULT_SALDO_ONLY = Path("reports/saldo-only.jsonl")
DEFAULT_REPORT = Path("reports/saol14-saldo-comparison.json")

SALDO_POS_TO_UPOS = {
    "nn": "NOUN",
    "nnm": "NOUN",
    "nna": "NOUN",
    "pm": "PROPN",
    "vb": "VERB",
    "av": "ADJ",
    "ab": "ADV",
    "pn": "PRON",
    "dt": "DET",
    "pp": "ADP",
    "kn": "CCONJ",
    "sn": "SCONJ",
    "in": "INTJ",
    "rg": "NUM",
    "hp": "PRON",
    "ha": "ADV",
    "hd": "DET",
    "ie": "PART",
    "pc": "ADJ",
    "al": "X",
}


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _normalise(value: str) -> str:
    return unicodedata.normalize("NFC", value.strip())


def _key(value: str) -> str:
    return _normalise(value).casefold()


def _feature_values(element: ET.Element, names: set[str]) -> list[str]:
    values: list[str] = []
    wanted = {name.casefold() for name in names}
    for node in element.iter():
        local = _local_name(node.tag).casefold()
        if local in wanted and node.text:
            values.append(_normalise(node.text))
        for attribute, value in node.attrib.items():
            attr = _local_name(attribute).casefold()
            if attr in wanted:
                values.append(_normalise(value))
            elif attr in {"att", "name"} and value.casefold() in wanted:
                feature_value = node.attrib.get("val") or node.attrib.get("value")
                if feature_value:
                    values.append(_normalise(feature_value))
    return [value for value in values if value]


def _written_forms(element: ET.Element) -> list[str]:
    return _feature_values(element, {"writtenform"})


def _saldo_pos(element: ET.Element) -> str:
    candidates = _feature_values(element, {"partofspeech", "pos", "wordclass"})
    entry_id = element.attrib.get("id", "")
    if entry_id:
        match = re.search(r"\.\.([a-z]+)(?:\.|$)", entry_id.casefold())
        if match:
            candidates.append(match.group(1))

    known_upos = set(SALDO_POS_TO_UPOS.values())
    for candidate in candidates:
        compact = candidate.casefold().strip().rstrip(".")
        if compact.upper() in known_upos:
            return compact.upper()
        if compact in SALDO_POS_TO_UPOS:
            return SALDO_POS_TO_UPOS[compact]
    return ""


def _saol_upos(record: dict[str, Any]) -> str:
    """Resolve SAOL word class from the ordkl head, never from inflection text."""

    # ``ordkl`` contains both the grammatical label and, after markup, the
    # paradigm text.  Searching the whole field makes words inside the paradigm
    # look like word-class labels: e.g. ``v. <i>fick konjunktiv: ...</i>`` used
    # to hit ``konj`` and become CCONJ.  Only the head before the first tag is
    # authoritative for word class.
    ordkl = _normalise(str(record.get("ordkl", ""))).split("<", 1)[0].strip().casefold()
    rules = (
        (("namn",), "PROPN"),
        (("interj",), "INTJ"),
        (("prep",), "ADP"),
        (("konj", "samordnande"), "CCONJ"),
        (("subj", "underordnande"), "SCONJ"),
        (("pron",), "PRON"),
        (("räkn", "räkneord"), "NUM"),
        (("adv",), "ADV"),
        (("adj", "adjektiv"), "ADJ"),
        (("rxv", "ptv", "verb"), "VERB"),
        (("subst", "substantiv"), "NOUN"),
    )
    for markers, upos in rules:
        if any(marker in ordkl for marker in markers):
            return upos
    if re.match(r"^s\.(?:\s|<|$)", ordkl):
        return "NOUN"
    if re.match(r"^v\.(?:\s|<|$)", ordkl):
        return "VERB"
    return _normalise(str(record.get("upos", ""))).upper()


def _is_affix_entry(record: dict[str, Any], lemma: str) -> bool:
    ordkl = _normalise(str(record.get("ordkl", ""))).casefold()
    return (
        lemma.startswith("-")
        or lemma.endswith("-")
        or "slutled" in ordkl
        or "i sms." in ordkl
        or "i sms " in ordkl
    )


def read_saldo(path: Path) -> dict[str, list[dict[str, Any]]]:
    """Read SALDO analyses grouped by lemma without loading the full XML tree."""
    entries: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for _, element in ET.iterparse(path, events=("end",)):
        if _local_name(element.tag).casefold() != "lexicalentry":
            continue
        lemma_forms: list[str] = []
        for child in element:
            if _local_name(child.tag).casefold() == "lemma":
                lemma_forms.extend(_written_forms(child))
        all_forms = set(_written_forms(element))
        if not lemma_forms and all_forms:
            lemma_forms = [sorted(all_forms, key=str.casefold)[0]]
        analysis = {
            "id": element.attrib.get("id", ""),
            "upos": _saldo_pos(element),
            "lemmas": set(lemma_forms),
            "forms": all_forms,
        }
        for lemma in lemma_forms:
            entries[_key(lemma)].append(analysis)
        element.clear()
    return dict(entries)


def _build_form_index(
    saldo: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    form_index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen: set[tuple[str, int]] = set()
    for analyses in saldo.values():
        for analysis in analyses:
            identity = id(analysis)
            for form in analysis["forms"]:
                form_key = _key(form)
                marker = (form_key, identity)
                if marker in seen:
                    continue
                seen.add(marker)
                form_index[form_key].append(analysis)
    return dict(form_index)


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def compare_sources(
    saol_path: Path,
    saldo_path: Path,
    target_path: Path,
    saol_only_path: Path,
    ambiguous_path: Path,
    saldo_only_path: Path,
    report_path: Path,
) -> dict[str, Any]:
    saldo = read_saldo(saldo_path)
    form_index = _build_form_index(saldo)
    target_forms: set[str] = set()
    matched_saldo_lemmas: set[str] = set()
    saol_only: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []
    filtered_affix_records = 0
    source_records = 0
    compared_records = 0
    matched_records = 0
    unknown_pos_matched_records = 0
    inferred_pos_matched_records = 0
    form_matched_records = 0

    for record in read_jsonl(saol_path):
        source_records += 1
        lemma = _normalise(str(record.get("normaliserat_ord", "")))
        if not lemma:
            continue
        if _is_affix_entry(record, lemma):
            filtered_affix_records += 1
            continue
        compared_records += 1
        key = _key(lemma)
        upos = _saol_upos(record)
        candidates = list(saldo.get(key, []))
        matched_by_form = False
        if not candidates:
            generated = generate_entry(record)
            generated_forms = {_key(form) for form in generated.forms if form}
            form_candidates: list[dict[str, Any]] = []
            seen_ids: set[int] = set()
            for form_key in generated_forms:
                for candidate in form_index.get(form_key, []):
                    candidate_id = id(candidate)
                    if candidate_id in seen_ids:
                        continue
                    seen_ids.add(candidate_id)
                    form_candidates.append(candidate)
            candidate_lemmas = {
                _key(candidate_lemma)
                for candidate in form_candidates
                for candidate_lemma in candidate["lemmas"]
            }
            if len(candidate_lemmas) == 1:
                candidates = form_candidates
                matched_by_form = True

        exact = [candidate for candidate in candidates if candidate["upos"] == upos]
        inferred = False
        if not exact and upos in {"", "X"}:
            candidate_classes = {candidate["upos"] for candidate in candidates if candidate["upos"]}
            if len(candidate_classes) == 1:
                exact = candidates
                inferred = True
        if exact:
            matched_records += 1
            if upos in {"", "X"}:
                unknown_pos_matched_records += 1
            if inferred:
                inferred_pos_matched_records += 1
            if matched_by_form:
                form_matched_records += 1
            for candidate in exact:
                target_forms.update(candidate["forms"])
                matched_saldo_lemmas.update(_key(value) for value in candidate["lemmas"])
            continue

        if candidates:
            ambiguous.append(
                {
                    "lemma": lemma,
                    "saol_upos": upos,
                    "saldo_word_classes": sorted({candidate["upos"] for candidate in candidates}),
                    "saldo_lemmas": sorted(
                        {value for candidate in candidates for value in candidate["lemmas"]},
                        key=str.casefold,
                    ),
                }
            )
            continue

        generated = generate_entry(record)
        saol_only.append(
            {
                "lemma": lemma,
                "saol_upos": upos,
                "forms": sorted(set(generated.forms), key=str.casefold),
                "reason": "no_saldo_lemma_or_unique_form",
            }
        )

    saldo_only: list[dict[str, Any]] = []
    for key, analyses in saldo.items():
        if key in matched_saldo_lemmas:
            continue
        saldo_only.append(
            {
                "lemmas": sorted(
                    {value for analysis in analyses for value in analysis["lemmas"]},
                    key=str.casefold,
                ),
                "word_classes": sorted({analysis["upos"] for analysis in analyses}),
                "forms": sorted(
                    {value for analysis in analyses for value in analysis["forms"]},
                    key=str.casefold,
                ),
            }
        )

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text("\n".join(sorted(target_forms, key=str.casefold)) + "\n", encoding="utf-8")
    _write_jsonl(saol_only_path, saol_only)
    _write_jsonl(ambiguous_path, ambiguous)
    _write_jsonl(saldo_only_path, saldo_only)

    report = {
        "saol_source_records": source_records,
        "saol_filtered_affix_records": filtered_affix_records,
        "saol_compared_records": compared_records,
        "saol_matched_records": matched_records,
        "saol_unknown_pos_matched_records": unknown_pos_matched_records,
        "saol_inferred_pos_matched_records": inferred_pos_matched_records,
        "saol_form_matched_records": form_matched_records,
        "saol_only_records": len(saol_only),
        "ambiguous_records": len(ambiguous),
        "saldo_only_lemmas": len(saldo_only),
        "target_unique_forms": len(target_forms),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare SAOL and SALDO sources")
    parser.add_argument("--saol", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--saldo", type=Path, default=DEFAULT_SALDO)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--saol-only", type=Path, default=DEFAULT_SAOL_ONLY)
    parser.add_argument("--ambiguous", type=Path, default=DEFAULT_AMBIGUOUS)
    parser.add_argument("--saldo-only", type=Path, default=DEFAULT_SALDO_ONLY)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    report = compare_sources(
        args.saol,
        args.saldo,
        args.target,
        args.saol_only,
        args.ambiguous,
        args.saldo_only,
        args.report,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
