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
    "nn": "NOUN", "nnm": "NOUN", "nna": "NOUN", "pm": "PROPN",
    "vb": "VERB", "av": "ADJ", "ab": "ADV", "pn": "PRON",
    "dt": "DET", "pp": "ADP", "kn": "CCONJ", "sn": "SCONJ",
    "in": "INTJ", "rg": "NUM", "hp": "PRON", "ha": "ADV",
    "hd": "DET", "ie": "PART", "pc": "ADJ", "al": "X",
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

    ordkl = _normalise(str(record.get("ordkl", ""))).split("<", 1)[0].strip().casefold()
    rules = (
        (("namn",), "PROPN"), (("interj",), "INTJ"), (("prep",), "ADP"),
        (("konj", "samordnande"), "CCONJ"), (("subj", "underordnande"), "SCONJ"),
        (("pron",), "PRON"), (("räkn", "räkneord"), "NUM"), (("adv",), "ADV"),
        (("adj", "adjektiv"), "ADJ"), (("rxv", "ptv", "verb"), "VERB"),
        (("subst", "substantiv"), "NOUN"),
    )
    for markers, upos in rules:
        if any(marker in ordkl for marker in markers):
            return upos
    if re.match(r"^s\.(?:\s|$)", ordkl):
        return "NOUN"
    if re.match(r"^v\.(?:\s|$)", ordkl):
        return "VERB"
    return _normalise(str(record.get("upos", ""))).upper()


def _is_affix_entry(record: dict[str, Any], lemma: str) -> bool:
    ordkl = _normalise(str(record.get("ordkl", ""))).casefold()
    return (
        lemma.startswith("-") or lemma.endswith("-") or "slutled" in ordkl
        or "i sms." in ordkl or "i sms " in ordkl
    )


def read_saldo(path: Path) -> dict[str, list[dict[str, Any]]]:
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


def _build_form_index(saldo: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    form_index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen: set[tuple[str, int]] = set()
    for analyses in saldo.values():
        for analysis in analyses:
            identity = id(analysis)
            for form in analysis["forms"]:
                marker = (_key(form), identity)
                if marker not in seen:
                    seen.add(marker)
                    form_index[marker[0]].append(analysis)
    return dict(form_index)


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _add_match(
    analyses: Iterable[dict[str, Any]],
    target_forms: set[str],
    matched_saldo_lemmas: set[str],
) -> None:
    for analysis in analyses:
        target_forms.update(analysis["forms"])
        matched_saldo_lemmas.update(_key(value) for value in analysis["lemmas"])


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
    saol_lemma_keys: set[str] = set()
    matched_saldo_lemmas: set[str] = set()
    saol_only: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []
    filtered_affix_records = source_records = compared_records = matched_records = 0
    unknown_pos_matched_records = inferred_pos_matched_records = form_matched_records = 0

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
        saol_lemma_keys.add(key)
        upos = _saol_upos(record)
        candidates = list(saldo.get(key, []))

        if candidates:
            exact = [candidate for candidate in candidates if candidate["upos"] == upos]
            if upos not in {"", "X"} and exact:
                matched_records += 1
                _add_match(exact, target_forms, matched_saldo_lemmas)
                continue

            unknown = [candidate for candidate in candidates if not candidate["upos"]]
            if upos not in {"", "X"} and len(unknown) == 1:
                matched_records += 1
                unknown_pos_matched_records += 1
                _add_match(unknown, target_forms, matched_saldo_lemmas)
                continue

            candidate_classes = {candidate["upos"] for candidate in candidates}
            if upos in {"", "X"} and len(candidate_classes) == 1 and "" not in candidate_classes:
                matched_records += 1
                inferred_pos_matched_records += 1
                _add_match(candidates, target_forms, matched_saldo_lemmas)
                continue

            ambiguous.append({
                "lemma": lemma,
                "saol_upos": upos,
                "saldo_word_classes": sorted({candidate["upos"] for candidate in candidates}),
                "saldo_lemmas": sorted(
                    {value for candidate in candidates for value in candidate["lemmas"]},
                    key=str.casefold,
                ),
            })
            continue

        # No SALDO lemma match.  The SAOL lemma itself may already be an
        # inflected SALDO form (e.g. ``kvisten`` -> lemma ``kvist``).  This is
        # stronger and safer than trying to invent forms from an unsupported
        # SAOL row, and it also works for rows with no inflection text.
        form_candidates = [
            candidate
            for candidate in form_index.get(key, [])
            if upos not in {"", "X"} and candidate["upos"] == upos
        ]
        if len(form_candidates) == 1:
            matched_records += 1
            form_matched_records += 1
            _add_match(form_candidates, target_forms, matched_saldo_lemmas)
            continue

        generated = generate_entry(record)
        saol_only.append({
            "lemma": lemma,
            "saol_upos": upos,
            "forms": sorted(set(generated.forms), key=str.casefold) if generated is not None else [lemma],
            "reason": "no_saldo_lemma_or_unique_form",
        })

    saldo_only: list[dict[str, Any]] = []
    covered_saldo_keys = saol_lemma_keys | matched_saldo_lemmas
    for key, analyses in saldo.items():
        if key in covered_saldo_keys:
            continue
        saldo_only.append({
            "lemmas": sorted(
                {value for analysis in analyses for value in analysis["lemmas"]},
                key=str.casefold,
            ),
            "word_classes": sorted({analysis["upos"] for analysis in analyses}),
            "forms": sorted(
                {value for analysis in analyses for value in analysis["forms"]},
                key=str.casefold,
            ),
        })

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(
        "\n".join(sorted(target_forms, key=str.casefold)) + ("\n" if target_forms else ""),
        encoding="utf-8",
    )
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
        args.saol, args.saldo, args.target, args.saol_only,
        args.ambiguous, args.saldo_only, args.report,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
