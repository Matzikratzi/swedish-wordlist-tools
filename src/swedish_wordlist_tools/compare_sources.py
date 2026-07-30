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
    """Resolve SAOL word class primarily from the more detailed ordkl field."""
    ordkl = _normalise(str(record.get("ordkl", ""))).casefold()
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
                if marker not in seen:
                    form_index[form_key].append(analysis)
                    seen.add(marker)
    return dict(form_index)


def _saol_row(record: dict[str, Any], lemma: str) -> dict[str, Any]:
    generated = generate_entry(record)
    return {
        "lemma": lemma,
        "homonym_number": str(record.get("homonr", "")),
        "record_id": str(record.get("id") or record.get("subnr") or ""),
        "upos": _saol_upos(record),
        "source_upos": str(record.get("upos", "")),
        "ordkl": str(record.get("ordkl", "")),
        "notation": str(record.get("text", "")),
        "generated_forms": list(generated.forms) if generated else [],
        "source": str(record.get("source", "")),
    }


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _saldo_lemma_keys(analyses: Iterable[dict[str, Any]]) -> set[str]:
    return {
        _key(lemma)
        for analysis in analyses
        for lemma in analysis["lemmas"]
        if lemma
    }


def _add_match(
    analyses: Iterable[dict[str, Any]],
    target_forms: set[str],
    matched_saldo_lemma_keys: set[str],
) -> None:
    chosen = list(analyses)
    matched_saldo_lemma_keys.update(_saldo_lemma_keys(chosen))
    for analysis in chosen:
        target_forms.update(analysis["forms"])


def compare_sources(
    saol_path: Path,
    saldo_path: Path,
    target_path: Path = DEFAULT_TARGET,
    saol_only_path: Path = DEFAULT_SAOL_ONLY,
    ambiguous_path: Path = DEFAULT_AMBIGUOUS,
    saldo_only_path: Path = DEFAULT_SALDO_ONLY,
    report_path: Path = DEFAULT_REPORT,
) -> dict[str, Any]:
    saldo = read_saldo(saldo_path)
    saldo_forms = _build_form_index(saldo)
    saol_lemma_keys: set[str] = set()
    matched_saldo_lemma_keys: set[str] = set()
    target_forms: set[str] = set()
    saol_only: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []
    matched_records = 0
    unknown_pos_matched_records = 0
    inferred_saol_pos_matched_records = 0
    form_matched_records = 0
    filtered_affix_records = 0
    source_records = 0

    for record in read_jsonl(saol_path):
        source_records += 1
        lemma = _normalise(str(record.get("normaliserat_ord", "")))
        if not lemma:
            continue
        if _is_affix_entry(record, lemma):
            filtered_affix_records += 1
            continue

        lemma_key = _key(lemma)
        saol_lemma_keys.add(lemma_key)
        saol_upos = _saol_upos(record)
        analyses = saldo.get(lemma_key, [])

        if analyses:
            matching = [analysis for analysis in analyses if analysis["upos"] == saol_upos]
            if saol_upos and saol_upos != "X" and matching:
                matched_records += 1
                _add_match(matching, target_forms, matched_saldo_lemma_keys)
                continue

            unknown = [analysis for analysis in analyses if not analysis["upos"]]
            if saol_upos and saol_upos != "X" and len(unknown) == 1:
                matched_records += 1
                unknown_pos_matched_records += 1
                _add_match(unknown, target_forms, matched_saldo_lemma_keys)
                continue

            saldo_classes = {analysis["upos"] for analysis in analyses}
            if saol_upos in {"", "X"} and len(saldo_classes) == 1 and "" not in saldo_classes:
                matched_records += 1
                inferred_saol_pos_matched_records += 1
                _add_match(analyses, target_forms, matched_saldo_lemma_keys)
                continue

            available_classes = sorted(
                {analysis["upos"] or "UNKNOWN" for analysis in analyses},
                key=str.casefold,
            )
            row = _saol_row(record, lemma)
            row.update(
                {
                    "reason": "lemma_match_but_word_class_not_resolved",
                    "saldo_word_classes": available_classes,
                    "saldo_analyses": [
                        {
                            "id": analysis["id"],
                            "upos": analysis["upos"],
                            "lemmas": sorted(analysis["lemmas"], key=str.casefold),
                            "forms": sorted(analysis["forms"], key=str.casefold),
                        }
                        for analysis in analyses
                    ],
                }
            )
            ambiguous.append(row)
            continue

        form_candidates = [
            analysis
            for analysis in saldo_forms.get(lemma_key, [])
            if saol_upos and saol_upos != "X" and analysis["upos"] == saol_upos
        ]
        if len(form_candidates) == 1:
            matched_records += 1
            form_matched_records += 1
            _add_match(form_candidates, target_forms, matched_saldo_lemma_keys)
            continue

        row = _saol_row(record, lemma)
        if form_candidates:
            row["reason"] = "multiple_saldo_form_matches"
            row["saldo_form_analyses"] = [
                {
                    "id": analysis["id"],
                    "upos": analysis["upos"],
                    "lemmas": sorted(analysis["lemmas"], key=str.casefold),
                    "forms": sorted(analysis["forms"], key=str.casefold),
                }
                for analysis in form_candidates
            ]
            ambiguous.append(row)
        else:
            row["reason"] = "no_saldo_lemma_or_unique_form"
            saol_only.append(row)

    saldo_only = []
    covered_saldo_keys = saol_lemma_keys | matched_saldo_lemma_keys
    for lemma_key, analyses in saldo.items():
        if lemma_key in covered_saldo_keys:
            continue
        lemmas = sorted(
            {lemma for analysis in analyses for lemma in analysis["lemmas"]},
            key=str.casefold,
        )
        saldo_only.append(
            {
                "lemmas": lemmas,
                "analyses": [
                    {
                        "id": analysis["id"],
                        "upos": analysis["upos"],
                        "forms": sorted(analysis["forms"], key=str.casefold),
                    }
                    for analysis in analyses
                ],
            }
        )

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(
        "\n".join(sorted(target_forms, key=str.casefold)) + ("\n" if target_forms else ""),
        encoding="utf-8",
    )
    _write_jsonl(saol_only_path, sorted(saol_only, key=lambda row: row["lemma"].casefold()))
    _write_jsonl(ambiguous_path, sorted(ambiguous, key=lambda row: row["lemma"].casefold()))
    _write_jsonl(
        saldo_only_path,
        sorted(saldo_only, key=lambda row: row["lemmas"][0].casefold() if row["lemmas"] else ""),
    )

    compared_records = source_records - filtered_affix_records
    report = {
        "saol_source_records": source_records,
        "saol_filtered_affix_records": filtered_affix_records,
        "saol_compared_records": compared_records,
        "saol_matched_records": matched_records,
        "saol_unknown_pos_matched_records": unknown_pos_matched_records,
        "saol_inferred_pos_matched_records": inferred_saol_pos_matched_records,
        "saol_form_matched_records": form_matched_records,
        "saol_only_records": len(saol_only),
        "ambiguous_records": len(ambiguous),
        "saldo_lemmas": len(saldo),
        "saldo_only_lemmas": len(saldo_only),
        "target_unique_forms": len(target_forms),
        "target": str(target_path),
        "saol_only": str(saol_only_path),
        "ambiguous": str(ambiguous_path),
        "saldo_only": str(saldo_only_path),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a SAOL14-only target list using matching SALDO inflections"
    )
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("saldo", nargs="?", type=Path, default=DEFAULT_SALDO)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--saol-only", type=Path, default=DEFAULT_SAOL_ONLY)
    parser.add_argument("--ambiguous", type=Path, default=DEFAULT_AMBIGUOUS)
    parser.add_argument("--saldo-only", type=Path, default=DEFAULT_SALDO_ONLY)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = compare_sources(
        args.saol,
        args.saldo,
        args.target,
        args.saol_only,
        args.ambiguous,
        args.saldo_only,
        args.report,
    )
    print(f"SAOL-poster: {report['saol_source_records']}")
    print(f"Bortfiltrerade affix/sammansättningsposter: {report['saol_filtered_affix_records']}")
    print(f"Jämförda SAOL-poster: {report['saol_compared_records']}")
    print(f"Säkert matchade SAOL-poster: {report['saol_matched_records']}")
    print(f"  via okänd SALDO-ordklass: {report['saol_unknown_pos_matched_records']}")
    print(f"  via entydig SALDO-ordklass för okänd SAOL-klass: {report['saol_inferred_pos_matched_records']}")
    print(f"  via unik SALDO-böjningsform: {report['saol_form_matched_records']}")
    print(f"Endast i SAOL: {report['saol_only_records']}")
    print(f"Tvetydiga lemmaträffar: {report['ambiguous_records']}")
    print(f"Endast i SALDO: {report['saldo_only_lemmas']}")
    print(f"Former i mållistan: {report['target_unique_forms']}")
    print(f"Mållista: {report['target']}")
    print(f"SAOL-only: {report['saol_only']}")
    print(f"Tvetydiga: {report['ambiguous']}")
    print(f"SALDO-only: {report['saldo_only']}")


if __name__ == "__main__":
    main()
