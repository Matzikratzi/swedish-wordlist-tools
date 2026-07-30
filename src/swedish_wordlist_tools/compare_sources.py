from __future__ import annotations

import argparse
import json
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
DEFAULT_SALDO_ONLY = Path("reports/saldo-only.jsonl")
DEFAULT_REPORT = Path("reports/saol14-saldo-comparison.json")


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _normalise(value: str) -> str:
    return unicodedata.normalize("NFC", value.strip())


def _key(value: str) -> str:
    return _normalise(value).casefold()


def _written_forms(element: ET.Element) -> list[str]:
    forms: list[str] = []
    for node in element.iter():
        local = _local_name(node.tag).casefold()
        if local == "writtenform" and node.text:
            forms.append(_normalise(node.text))
        for attribute, value in node.attrib.items():
            attr = _local_name(attribute).casefold()
            if attr == "writtenform":
                forms.append(_normalise(value))
            elif attr in {"att", "name"} and value.casefold() == "writtenform":
                form = node.attrib.get("val") or node.attrib.get("value")
                if form:
                    forms.append(_normalise(form))
    return [form for form in forms if form]


def read_saldo(path: Path) -> dict[str, dict[str, Any]]:
    """Read SALDO entries grouped by lemma, without loading the XML tree at once."""
    entries: dict[str, dict[str, Any]] = {}
    for _, element in ET.iterparse(path, events=("end",)):
        if _local_name(element.tag).casefold() != "lexicalentry":
            continue

        lemma_forms: list[str] = []
        for child in element:
            if _local_name(child.tag).casefold() == "lemma":
                lemma_forms.extend(_written_forms(child))
        all_forms = _written_forms(element)
        if not lemma_forms and all_forms:
            lemma_forms = all_forms[:1]

        for lemma in lemma_forms:
            lemma_key = _key(lemma)
            bucket = entries.setdefault(lemma_key, {"lemmas": set(), "forms": set()})
            bucket["lemmas"].add(lemma)
            bucket["forms"].update(all_forms)
        element.clear()
    return entries


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def compare_sources(
    saol_path: Path,
    saldo_path: Path,
    target_path: Path = DEFAULT_TARGET,
    saol_only_path: Path = DEFAULT_SAOL_ONLY,
    saldo_only_path: Path = DEFAULT_SALDO_ONLY,
    report_path: Path = DEFAULT_REPORT,
) -> dict[str, Any]:
    saldo = read_saldo(saldo_path)
    saol_keys: set[str] = set()
    target_forms: set[str] = set()
    saol_only: list[dict[str, Any]] = []
    matched_records = 0
    source_records = 0

    for record in read_jsonl(saol_path):
        source_records += 1
        lemma = _normalise(str(record.get("normaliserat_ord", "")))
        if not lemma:
            continue
        lemma_key = _key(lemma)
        saol_keys.add(lemma_key)
        saldo_entry = saldo.get(lemma_key)
        if saldo_entry is not None:
            matched_records += 1
            target_forms.update(saldo_entry["forms"])
            continue

        generated = generate_entry(record)
        saol_only.append({
            "lemma": lemma,
            "record_id": str(record.get("id") or record.get("subnr") or ""),
            "upos": str(record.get("upos", "")),
            "ordkl": str(record.get("ordkl", "")),
            "notation": str(record.get("text", "")),
            "generated_forms": list(generated.forms) if generated else [],
            "source": str(record.get("source", "")),
        })

    saldo_only = [
        {
            "lemmas": sorted(entry["lemmas"], key=str.casefold),
            "forms": sorted(entry["forms"], key=str.casefold),
        }
        for lemma_key, entry in saldo.items()
        if lemma_key not in saol_keys
    ]

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(
        "\n".join(sorted(target_forms, key=str.casefold)) + ("\n" if target_forms else ""),
        encoding="utf-8",
    )
    _write_jsonl(saol_only_path, sorted(saol_only, key=lambda row: row["lemma"].casefold()))
    _write_jsonl(saldo_only_path, sorted(saldo_only, key=lambda row: row["lemmas"][0].casefold()))

    report = {
        "saol_source_records": source_records,
        "saol_matched_records": matched_records,
        "saol_only_records": len(saol_only),
        "saldo_lemmas": len(saldo),
        "saldo_only_lemmas": len(saldo_only),
        "target_unique_forms": len(target_forms),
        "target": str(target_path),
        "saol_only": str(saol_only_path),
        "saldo_only": str(saldo_only_path),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a SAOL14-only target list using SALDO inflection forms"
    )
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("saldo", nargs="?", type=Path, default=DEFAULT_SALDO)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--saol-only", type=Path, default=DEFAULT_SAOL_ONLY)
    parser.add_argument("--saldo-only", type=Path, default=DEFAULT_SALDO_ONLY)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = compare_sources(
        args.saol, args.saldo, args.target, args.saol_only, args.saldo_only, args.report
    )
    print(f"SAOL-poster: {report['saol_source_records']}")
    print(f"Matchade SAOL-poster: {report['saol_matched_records']}")
    print(f"Endast i SAOL: {report['saol_only_records']}")
    print(f"Endast i SALDO: {report['saldo_only_lemmas']}")
    print(f"Former i mållistan: {report['target_unique_forms']}")
    print(f"Mållista: {report['target']}")
    print(f"SAOL-only: {report['saol_only']}")
    print(f"SALDO-only: {report['saldo_only']}")


if __name__ == "__main__":
    main()
