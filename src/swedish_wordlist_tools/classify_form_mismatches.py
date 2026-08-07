from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

DEFAULT_INPUT = Path("reports/saol14-direct-form-validation.jsonl")
DEFAULT_JSONL = Path("reports/saol14-form-mismatch-classification.jsonl")
DEFAULT_SUMMARY = Path("reports/saol14-form-mismatch-classification-summary.json")
DEFAULT_TEXT = Path("reports/saol14-form-mismatch-classification.txt")
TARGET_STATUS = "form_set_mismatch"

SALDO_MISSING_PLURAL = "saldo_missing_plural"
UNCLASSIFIED = "unclassified"


def _casefolded(values: Iterable[object]) -> set[str]:
    return {str(value).casefold() for value in values}


def _expected_en_er_plural(lemma: str) -> set[str]:
    return {
        lemma + "er",
        lemma + "ers",
        lemma + "erna",
        lemma + "ernas",
    }


def classify_row(row: dict[str, Any]) -> tuple[str, str]:
    """Classify a mismatch only when the source difference is mechanically certain.

    `+en +er` explicitly states the plural in SAOL.  If the only forms present in
    the canonical SAOL generation but absent from SALDO are exactly that plural
    paradigm, SALDO is simply missing the SAOL-attested plural forms.  No claim is
    made about why SALDO omits them.
    """

    if str(row.get("status", "")) != TARGET_STATUS:
        return UNCLASSIFIED, "not_a_form_set_mismatch"

    upos = str(row.get("upos", "")).upper()
    notation = str(row.get("notation", "")).strip()
    lemma = str(row.get("lemma", "")).casefold()
    extra = _casefolded(row.get("extra_from_saol", ()))
    missing = _casefolded(row.get("missing_from_saol", ()))

    if (
        upos == "NOUN"
        and notation == "+en +er"
        and lemma
        and not missing
        and extra == _expected_en_er_plural(lemma)
    ):
        return (
            SALDO_MISSING_PLURAL,
            "SAOL notation +en +er explicitly supplies plural +er; SALDO lacks exactly the plural paradigm",
        )

    return UNCLASSIFIED, "no_verified_general_classification"


def classify_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in rows:
        if str(row.get("status", "")) != TARGET_STATUS:
            continue
        classification, rationale = classify_row(row)
        result.append(
            {
                **row,
                "mismatch_classification": classification,
                "classification_rationale": rationale,
            }
        )
    return result


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


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(str(row["mismatch_classification"]) for row in rows)
    unclassified_upos = Counter(
        str(row.get("upos", ""))
        for row in rows
        if row["mismatch_classification"] == UNCLASSIFIED
    )
    return {
        "mismatch_records": len(rows),
        "classification_counts": dict(sorted(counts.items(), key=lambda item: (-item[1], item[0]))),
        "classified_records": len(rows) - counts.get(UNCLASSIFIED, 0),
        "unclassified_records": counts.get(UNCLASSIFIED, 0),
        "unclassified_upos_counts": dict(
            sorted(unclassified_upos.items(), key=lambda item: (-item[1], item[0]))
        ),
    }


def render_text(summary: dict[str, Any]) -> str:
    lines = [
        f"Mismatchposter: {summary['mismatch_records']}",
        f"Klassificerade: {summary['classified_records']}",
        f"Oklassificerade: {summary['unclassified_records']}",
        "",
        "Klassningar:",
    ]
    for name, count in summary["classification_counts"].items():
        lines.append(f"{count:5}  {name}")
    lines.extend(["", "Oklassificerade per ordklass:"])
    if not summary["unclassified_upos_counts"]:
        lines.append("  (inga)")
    else:
        for upos, count in summary["unclassified_upos_counts"].items():
            lines.append(f"{count:5}  {upos}")
    return "\n".join(lines) + "\n"


def classify_file(
    input_path: Path = DEFAULT_INPUT,
    *,
    jsonl_path: Path = DEFAULT_JSONL,
    summary_path: Path = DEFAULT_SUMMARY,
    text_path: Path = DEFAULT_TEXT,
) -> dict[str, Any]:
    rows = classify_rows(read_jsonl(input_path))
    write_jsonl(jsonl_path, rows)
    summary = build_summary(rows)
    summary.update(
        {
            "input": str(input_path),
            "jsonl": str(jsonl_path),
            "summary": str(summary_path),
            "text": str(text_path),
        }
    )
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    text_path.parent.mkdir(parents=True, exist_ok=True)
    text_path.write_text(render_text(summary), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Klassificera verifierade SAOL–SALDO-formskillnader utan att ändra generatorn"
    )
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    args = parser.parse_args()
    summary = classify_file(
        args.input,
        jsonl_path=args.jsonl,
        summary_path=args.summary,
        text_path=args.text,
    )
    print(f"Mismatchposter: {summary['mismatch_records']}")
    print(f"Klassificerade: {summary['classified_records']}")
    print(f"Oklassificerade: {summary['unclassified_records']}")
    for name, count in summary["classification_counts"].items():
        print(f"{name}: {count}")
    print(f"Text: {summary['text']}")
    print(f"JSONL: {summary['jsonl']}")


if __name__ == "__main__":
    main()
