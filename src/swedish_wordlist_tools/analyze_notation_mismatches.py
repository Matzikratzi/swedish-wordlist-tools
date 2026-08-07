from __future__ import annotations

import argparse
import json
import unicodedata
from pathlib import Path
from typing import Any, Iterable

from .compare_sources import read_saldo

DEFAULT_VALIDATION = Path("reports/saol14-direct-form-validation.jsonl")
DEFAULT_SALDO = Path("data/raw/saldom.xml")
DEFAULT_TEXT = Path("reports/saol14-notation-mismatches.txt")
DEFAULT_JSON = Path("reports/saol14-notation-mismatches.json")
DEFAULT_NOTATION = "+n +er"


def _key(value: str) -> str:
    return unicodedata.normalize("NFC", value.strip()).casefold()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValueError(f"Ogiltig JSON på rad {number} i {path}") from error
    return rows


def analyse_rows(
    rows: Iterable[dict[str, Any]],
    saldo: dict[str, list[dict[str, Any]]],
    notation: str,
    status: str = "form_set_mismatch",
) -> dict[str, Any]:
    selected = [
        row
        for row in rows
        if row.get("status") == status and str(row.get("notation", "")) == notation
    ]
    selected.sort(
        key=lambda row: (
            str(row.get("lemma", "")).casefold(),
            str(row.get("homonym_number", "")),
        )
    )

    records: list[dict[str, Any]] = []
    for row in selected:
        lemma = str(row.get("lemma", ""))
        candidates = []
        for analysis in saldo.get(_key(lemma), []):
            candidates.append(
                {
                    "id": str(analysis.get("id", "")),
                    "upos": str(analysis.get("upos", "")),
                    "lemmas": sorted(analysis.get("lemmas", ()), key=str.casefold),
                    "forms": sorted(analysis.get("forms", ()), key=str.casefold),
                }
            )
        candidates.sort(key=lambda item: (item["upos"], item["id"], item["lemmas"]))

        records.append(
            {
                "lemma": lemma,
                "homonym_number": str(row.get("homonym_number", "")),
                "record_id": str(row.get("record_id", "")),
                "upos": str(row.get("upos", "")),
                "match_method": str(row.get("match_method", "")),
                "generated_forms": list(row.get("generated_forms", [])),
                "saldo_forms": list(row.get("saldo_forms", [])),
                "extra_from_saol": list(row.get("extra_from_saol", [])),
                "missing_from_saol": list(row.get("missing_from_saol", [])),
                "selected_saldo_ids": list(row.get("saldo_ids", [])),
                "selected_saldo_lemmas": list(row.get("saldo_lemmas", [])),
                "saldo_candidates": candidates,
            }
        )

    return {
        "status": status,
        "notation": notation,
        "records": len(records),
        "items": records,
    }


def render_text(summary: dict[str, Any]) -> str:
    lines = [
        f"Status: {summary['status']}",
        f"SAOL-notation: {summary['notation']}",
        f"Poster: {summary['records']}",
    ]
    for index, item in enumerate(summary["items"], start=1):
        homonym = f" ({item['homonym_number']})" if item["homonym_number"] else ""
        lines.extend(
            [
                "",
                f"{index}. {item['lemma']}{homonym}",
                f"   UPOS: {item['upos']}",
                f"   Matchning: {item['match_method']}",
                "   SAOL-former: " + (", ".join(item["generated_forms"]) or "–"),
                "   Valda SALDO-former: " + (", ".join(item["saldo_forms"]) or "–"),
                "   Extra från SAOL: " + (", ".join(item["extra_from_saol"]) or "–"),
                "   Saknas från SAOL: " + (", ".join(item["missing_from_saol"]) or "–"),
                f"   SALDO-kandidater: {len(item['saldo_candidates'])}",
            ]
        )
        for candidate_index, candidate in enumerate(item["saldo_candidates"], start=1):
            selected = candidate["id"] in item["selected_saldo_ids"]
            marker = " [vald]" if selected else ""
            lines.extend(
                [
                    f"     {candidate_index}. {candidate['id'] or '(utan id)'} | {candidate['upos']}{marker}",
                    "        Lemma: " + (", ".join(candidate["lemmas"]) or "–"),
                    "        Former: " + (", ".join(candidate["forms"]) or "–"),
                ]
            )
    return "\n".join(lines) + "\n"


def analyse_file(
    validation_path: Path = DEFAULT_VALIDATION,
    saldo_path: Path = DEFAULT_SALDO,
    text_path: Path = DEFAULT_TEXT,
    json_path: Path = DEFAULT_JSON,
    notation: str = DEFAULT_NOTATION,
    status: str = "form_set_mismatch",
) -> dict[str, Any]:
    summary = analyse_rows(read_jsonl(validation_path), read_saldo(saldo_path), notation, status)
    summary.update(
        {
            "validation": str(validation_path),
            "saldo": str(saldo_path),
            "text": str(text_path),
            "json": str(json_path),
        }
    )
    text_path.parent.mkdir(parents=True, exist_ok=True)
    text_path.write_text(render_text(summary), encoding="utf-8")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Visa kvarvarande mismatch och alla SALDO-kandidater för en SAOL-notation"
    )
    parser.add_argument("--notation", default=DEFAULT_NOTATION)
    parser.add_argument("--status", default="form_set_mismatch")
    parser.add_argument("--validation", type=Path, default=DEFAULT_VALIDATION)
    parser.add_argument("--saldo", type=Path, default=DEFAULT_SALDO)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    summary = analyse_file(
        args.validation,
        args.saldo,
        args.text,
        args.json,
        args.notation,
        args.status,
    )
    print(f"Status: {summary['status']}")
    print(f"SAOL-notation: {summary['notation']}")
    print(f"Poster: {summary['records']}")
    print(f"Text: {summary['text']}")
    print(f"JSON: {summary['json']}")


if __name__ == "__main__":
    main()
