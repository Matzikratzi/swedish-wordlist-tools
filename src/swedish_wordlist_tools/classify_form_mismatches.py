from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .analyze_form_validation_axes import classify_axes

DEFAULT_INPUT = Path("reports/saol14-direct-form-validation.jsonl")
DEFAULT_JSONL = Path("reports/saol14-form-mismatch-classification.jsonl")
DEFAULT_SUMMARY = Path("reports/saol14-form-mismatch-classification-summary.json")
DEFAULT_TEXT = Path("reports/saol14-form-mismatch-classification.txt")
TARGET_STATUS = "form_set_mismatch"

SALDO_MISSING_PLURAL = "saldo_missing_plural"
SALDO_MISSING_DEFINITE_PLURAL = "saldo_missing_definite_plural"
SALDO_MISSING_DEFINITE_SINGULAR = "saldo_missing_definite_singular"
SALDO_ALTERNATIVE_DEFINITE_SINGULAR_MISSING_PLURAL = (
    "saldo_alternative_definite_singular_missing_plural"
)
SALDO_COMPETING_PLURAL_MISSING_DEFINITE_SINGULAR = (
    "saldo_competing_plural_missing_definite_singular"
)
SALDO_COMPETING_GENDER_AND_PLURAL = "saldo_competing_gender_and_plural"
SALDO_COMPETING_GENDER_AND_FULL_PLURAL = "saldo_competing_gender_and_full_plural"
SALDO_COMPETING_PLURAL_PARADIGM = "saldo_competing_plural_paradigm"
UNCLASSIFIED = "unclassified"


def _casefolded(values: Iterable[object]) -> set[str]:
    return {str(value).casefold() for value in values}


def _relative_form(lemma: str, form: object) -> str:
    lemma_folded = lemma.casefold()
    form_folded = str(form).casefold()
    if lemma_folded and form_folded.startswith(lemma_folded):
        return "+" + form_folded[len(lemma_folded) :]
    return "=" + form_folded


def _relative_forms(lemma: str, values: Iterable[object]) -> tuple[str, ...]:
    return tuple(sorted(_relative_form(lemma, value) for value in values))


def _suffixed_forms(lemma: str, suffixes: Iterable[str]) -> set[str]:
    return {lemma + suffix for suffix in suffixes}


def _is_paradigm_mismatch(row: dict[str, Any]) -> bool:
    materialized = str(row.get("paradigm_status") or "")
    if materialized:
        return materialized == TARGET_STATUS
    _coverage, paradigm, _reason = classify_axes(row)
    return paradigm == TARGET_STATUS


def classify_row(row: dict[str, Any]) -> tuple[str, str]:
    """Classify only mechanically certain SAOL–SALDO paradigm differences.

    A classification says what differs between the sources; it does not change
    the canonical SAOL generator and it does not speculate about why either
    source chose its paradigm. Lexical variant coverage is an independent axis
    and is deliberately excluded here unless a present variant also has a real
    paradigm mismatch.
    """

    if not _is_paradigm_mismatch(row):
        return UNCLASSIFIED, "not_a_paradigm_form_set_mismatch"

    upos = str(row.get("upos", "")).upper()
    notation = str(row.get("notation", "")).strip()
    lemma = str(row.get("lemma", "")).casefold()
    extra = _casefolded(row.get("extra_from_saol", ()))
    missing = _casefolded(row.get("missing_from_saol", ()))

    if upos != "NOUN" or not lemma:
        return UNCLASSIFIED, "no_verified_general_classification"

    explicit_plural_patterns = {
        "+en +er": ("er", "ers", "erna", "ernas"),
        "+en +ar": ("ar", "ars", "arna", "arnas"),
        "+t +n": ("n", "ns", "na", "nas"),
        "+n +r": ("r", "rs", "rna", "rnas"),
        "+n +er": ("er", "ers", "erna", "ernas"),
        "+et +er": ("er", "ers", "erna", "ernas"),
    }
    plural_suffixes = explicit_plural_patterns.get(notation)
    if (
        not missing
        and plural_suffixes is not None
        and extra == _suffixed_forms(lemma, plural_suffixes)
    ):
        return (
            SALDO_MISSING_PLURAL,
            f"SAOL notation {notation} explicitly supplies a plural paradigm; SALDO lacks exactly that paradigm",
        )

    definite_zero_plural_patterns = {
        "+et; pl. +": ("en", "ens"),
        "+en; pl. +": ("na", "nas"),
    }
    definite_plural_suffixes = definite_zero_plural_patterns.get(notation)
    if (
        not missing
        and definite_plural_suffixes is not None
        and extra == _suffixed_forms(lemma, definite_plural_suffixes)
    ):
        return (
            SALDO_MISSING_DEFINITE_PLURAL,
            f"SAOL notation {notation} has zero plural and canonical definite plural forms; SALDO lacks exactly those definite plural forms",
        )

    definite_singular_patterns = {
        "+en +er": ("en", "ens"),
        "+en": ("en", "ens"),
        "+et; pl. +": ("et", "ets"),
        "+en +er _ +n +er": ("n", "ns"),
        "+et el. +en": ("en", "ens"),
    }
    definite_singular_suffixes = definite_singular_patterns.get(notation)
    if (
        not missing
        and definite_singular_suffixes is not None
        and extra == _suffixed_forms(lemma, definite_singular_suffixes)
    ):
        return (
            SALDO_MISSING_DEFINITE_SINGULAR,
            f"SAOL notation {notation} explicitly supplies the definite singular form; SALDO lacks exactly that form and its genitive",
        )

    if notation == "+et; pl. +" and extra == _suffixed_forms(lemma, ("et", "ets")):
        for suffixes in (("ar", "ars", "arna", "arnas"), ("er", "ers", "erna", "ernas")):
            if missing == _suffixed_forms(lemma, suffixes):
                return (
                    SALDO_COMPETING_PLURAL_MISSING_DEFINITE_SINGULAR,
                    "SAOL explicitly has neuter definite singular and zero plural, while SALDO lacks that definite-singular pair and supplies exactly one regular plural paradigm",
                )

    if (
        notation == "+en +ar"
        and extra == _suffixed_forms(lemma, ("en", "ens", "ar", "ars", "arna", "arnas"))
        and missing == _suffixed_forms(lemma, ("et", "ets"))
    ):
        return (
            SALDO_COMPETING_GENDER_AND_PLURAL,
            "SAOL explicitly has common-gender definite singular plus -ar plural, while SALDO instead has exactly the neuter definite-singular pair",
        )

    if notation == "+et" and extra == _suffixed_forms(lemma, ("et", "ets")):
        for plural in (
            ("ar", "ars", "arna", "arnas"),
            ("er", "ers", "erna", "ernas"),
        ):
            if missing == _suffixed_forms(lemma, ("en", "ens", *plural)):
                return (
                    SALDO_COMPETING_GENDER_AND_FULL_PLURAL,
                    "SAOL notation +et supplies exactly the neuter definite-singular pair while SALDO supplies exactly common-gender definite singular plus one complete regular plural paradigm",
                )

    competing_plural_patterns = {
        "+en +er": (
            ("er", "ers", "erna", "ernas"),
            ("ar", "ars", "arna", "arnas"),
        ),
        "+en +ar": (
            ("ar", "ars", "arna", "arnas"),
            ("er", "ers", "erna", "ernas"),
        ),
    }
    competing = competing_plural_patterns.get(notation)
    if competing is not None:
        saol_plural, saldo_plural = competing
        if (
            extra == _suffixed_forms(lemma, saol_plural)
            and missing == _suffixed_forms(lemma, saldo_plural)
        ):
            return (
                SALDO_COMPETING_PLURAL_PARADIGM,
                f"SAOL notation {notation} explicitly supplies one complete regular plural paradigm while SALDO supplies exactly the competing regular plural paradigm",
            )

    alternative_definite_pairs = {
        "+n +er": (("en", "ens"),),
        "+et +er": (("t", "ts"), ("en", "ens")),
        "+en +ar": (("et", "ets"),),
        "+en +er": (("et", "ets"),),
    }
    alternative_pairs = alternative_definite_pairs.get(notation, ())
    if plural_suffixes is not None and extra == _suffixed_forms(lemma, plural_suffixes):
        for pair in alternative_pairs:
            if missing == _suffixed_forms(lemma, pair):
                return (
                    SALDO_ALTERNATIVE_DEFINITE_SINGULAR_MISSING_PLURAL,
                    f"SAOL notation {notation} explicitly supplies the plural paradigm that SALDO lacks, while SALDO has exactly one competing definite-singular pair",
                )

    return UNCLASSIFIED, "no_verified_general_classification"


def classify_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in rows:
        if not _is_paradigm_mismatch(row):
            continue
        coverage, paradigm, reason = classify_axes(row)
        classification, rationale = classify_row(row)
        result.append(
            {
                **row,
                "coverage_status": str(row.get("coverage_status") or coverage),
                "paradigm_status": str(row.get("paradigm_status") or paradigm),
                "paradigm_reason": str(row.get("paradigm_reason") or reason),
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


def _unclassified_groups(rows: list[dict[str, Any]], examples: int = 8) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, tuple[str, ...], tuple[str, ...]], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["mismatch_classification"] != UNCLASSIFIED:
            continue
        lemma = str(row.get("lemma", ""))
        key = (
            str(row.get("upos", "")).upper(),
            str(row.get("notation", "")),
            _relative_forms(lemma, row.get("extra_from_saol", ())),
            _relative_forms(lemma, row.get("missing_from_saol", ())),
        )
        grouped[key].append(row)

    groups: list[dict[str, Any]] = []
    for (upos, notation, extra, missing), members in grouped.items():
        members.sort(key=lambda row: (str(row.get("lemma", "")).casefold(), str(row.get("homonym_number", ""))))
        groups.append(
            {
                "upos": upos,
                "notation": notation,
                "count": len(members),
                "extra_pattern": list(extra),
                "missing_pattern": list(missing),
                "examples": [
                    {
                        "lemma": str(row.get("lemma", "")),
                        "homonym_number": str(row.get("homonym_number", "")),
                    }
                    for row in members[:examples]
                ],
            }
        )
    groups.sort(
        key=lambda group: (
            -int(group["count"]),
            str(group["upos"]),
            str(group["notation"]),
            tuple(group["extra_pattern"]),
            tuple(group["missing_pattern"]),
        )
    )
    return groups


def build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(str(row["mismatch_classification"]) for row in rows)
    unclassified_upos = Counter(
        str(row.get("upos", ""))
        for row in rows
        if row["mismatch_classification"] == UNCLASSIFIED
    )
    coverage_counts = Counter(str(row.get("coverage_status") or "") for row in rows)
    reason_counts = Counter(str(row.get("paradigm_reason") or "") for row in rows)
    return {
        "selection_axis": "paradigm_status",
        "paradigm_status": TARGET_STATUS,
        "mismatch_records": len(rows),
        "coverage_status_counts": dict(sorted(coverage_counts.items())),
        "paradigm_reason_counts": dict(sorted(reason_counts.items())),
        "classification_counts": dict(sorted(counts.items(), key=lambda item: (-item[1], item[0]))),
        "classified_records": len(rows) - counts.get(UNCLASSIFIED, 0),
        "unclassified_records": counts.get(UNCLASSIFIED, 0),
        "unclassified_upos_counts": dict(
            sorted(unclassified_upos.items(), key=lambda item: (-item[1], item[0]))
        ),
        "unclassified_groups": _unclassified_groups(rows),
    }


def render_text(summary: dict[str, Any]) -> str:
    lines = [
        f"Urval: {summary['selection_axis']}={summary['paradigm_status']}",
        f"Mismatchposter: {summary['mismatch_records']}",
        f"Klassificerade: {summary['classified_records']}",
        f"Oklassificerade: {summary['unclassified_records']}",
        "",
        "Varianttäckning bland paradigmmismatch:",
    ]
    for name, count in summary["coverage_status_counts"].items():
        lines.append(f"{count:5}  {name}")
    lines.extend(["", "Paradigmorsaker:"])
    for name, count in summary["paradigm_reason_counts"].items():
        lines.append(f"{count:5}  {name}")
    lines.extend(["", "Klassningar:"])
    for name, count in summary["classification_counts"].items():
        lines.append(f"{count:5}  {name}")
    lines.extend(["", "Oklassificerade per ordklass:"])
    if not summary["unclassified_upos_counts"]:
        lines.append("  (inga)")
    else:
        for upos, count in summary["unclassified_upos_counts"].items():
            lines.append(f"{count:5}  {upos}")

    lines.extend(["", "Största oklassificerade strukturer:"])
    groups = summary.get("unclassified_groups", [])
    if not groups:
        lines.append("  (inga)")
    for index, group in enumerate(groups[:30], start=1):
        extra = ", ".join(group["extra_pattern"]) or "–"
        missing = ", ".join(group["missing_pattern"]) or "–"
        examples = ", ".join(
            item["lemma"] + (f" ({item['homonym_number']})" if item["homonym_number"] else "")
            for item in group["examples"]
        )
        lines.extend(
            [
                "",
                f"{index}. {group['count']} | {group['upos']} | {group['notation'] or '(tomt)'}",
                f"   Extra från SAOL-generatorn: {extra}",
                f"   Saknas från SAOL-generatorn: {missing}",
                f"   Exempel: {examples}",
            ]
        )
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
        description="Klassificera verifierade SAOL–SALDO-paradigmskillnader utan att blanda in varianttäckning"
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
    print(f"Paradigmmismatchposter: {summary['mismatch_records']}")
    print(f"Klassificerade: {summary['classified_records']}")
    print(f"Oklassificerade: {summary['unclassified_records']}")
    for name, count in summary["classification_counts"].items():
        print(f"{name}: {count}")
    print(f"Oklassificerade strukturer: {len(summary['unclassified_groups'])}")
    print(f"Text: {summary['text']}")
    print(f"JSONL: {summary['jsonl']}")


if __name__ == "__main__":
    main()
