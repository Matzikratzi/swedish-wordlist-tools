from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .classify_form_mismatches import UNCLASSIFIED, classify_row

DEFAULT_INPUT = Path("reports/saol14-direct-form-validation.jsonl")
DEFAULT_JSONL = Path("reports/saol14-next-noun-batch-classification.jsonl")
DEFAULT_SUMMARY = Path("reports/saol14-next-noun-batch-classification-summary.json")
DEFAULT_TEXT = Path("reports/saol14-next-noun-batch-classification.txt")

SALDO_S_PLURAL_DEFINITE_PARADIGM = "saldo_s_plural_definite_paradigm"
SALDO_COMPETING_DEFINITE_SINGULAR_GENDER = "saldo_competing_definite_singular_gender"
SALDO_COMPETING_DEFINITE_SINGULAR_ALLOMORPH = "saldo_competing_definite_singular_allomorph"
SALDO_SIMPLE_VASEN_DEFINITE_PLURAL_PARADIGM = "saldo_simple_vasen_definite_plural_paradigm"
SALDO_MISSING_ALTERNATIVE_PLURAL = "saldo_missing_alternative_plural"
SALDO_MISSING_ZERO_PLURAL_DEFINITE = "saldo_missing_zero_plural_definite"
SALDO_ZERO_AND_S_PLURAL_DEFINITE_PARADIGM = "saldo_zero_and_s_plural_definite_paradigm"
SALDO_ZERO_VS_S_PLURAL_DEFINITE_PARADIGM = "saldo_zero_vs_s_plural_definite_paradigm"
SALDO_MISSING_ALTERNATIVE_NEUTER_DEFINITE_SINGULAR = "saldo_missing_alternative_neuter_definite_singular"


def _casefolded(values: Iterable[object]) -> set[str]:
    return {str(value).casefold() for value in values}


def _suffixed(lemma: str, suffixes: Iterable[str]) -> set[str]:
    return {lemma + suffix for suffix in suffixes}


def classify_batch_row(row: dict[str, Any]) -> tuple[str, str]:
    base, _ = classify_row(row)
    if base != UNCLASSIFIED:
        return UNCLASSIFIED, "already_classified"
    if str(row.get("upos", "")).upper() != "NOUN":
        return UNCLASSIFIED, "not_noun"
    if str(row.get("paradigm_status") or row.get("status") or "") != "form_set_mismatch":
        return UNCLASSIFIED, "not_form_set_mismatch"

    lemma = str(row.get("lemma", "")).casefold()
    notation = str(row.get("notation", "")).strip()
    if not lemma:
        return UNCLASSIFIED, "missing_lemma"
    extra = _casefolded(row.get("extra_from_saol", ()))
    missing = _casefolded(row.get("missing_from_saol", ()))

    # Simple -väsen articles without an alternative -väsende heading.
    if (
        notation == "+det; pl. +, best. pl. +dena"
        and lemma.endswith("väsen")
        and extra == _suffixed(lemma, ("dena", "denas"))
        and missing == _suffixed(lemma, ("a", "as"))
    ):
        return (
            SALDO_SIMPLE_VASEN_DEFINITE_PLURAL_PARADIGM,
            "SAOL simple -väsen paradigm has definite plural -väsendena/-väsendenas while SALDO has exactly the competing -väsea/-väseas forms",
        )

    # English-style -s plurals: SAOL and SALDO agree on +s as indefinite
    # plural but use different definite singular/plural continuations.
    s_plural_notations = {
        "+n; pl. +s",
        "+n; pl. + H +s",
        "+en; pl. +s",
        "+en; pl. +ar H +s",
    }
    if (
        notation in s_plural_notations
        and extra == _suffixed(lemma, ("sna", "snas"))
        and missing == _suffixed(lemma, ("sen", "sens", "sarna", "sarnas"))
    ):
        return (
            SALDO_S_PLURAL_DEFINITE_PARADIGM,
            "SAOL and SALDO share -s indefinite plural but have exactly competing definite singular/plural continuations: SAOL -sna/-snas versus SALDO -sen/-sens and -sarna/-sarnas",
        )

    # SAOL allows both zero plural and -s plural; SALDO uses the -s branch but
    # with different definite continuations.  The extra zero-plural definite
    # forms are therefore part of the same explicit alternative paradigm.
    if (
        notation == "+n; pl. + H +s"
        and extra == _suffixed(lemma, ("na", "nas", "sna", "snas"))
        and missing == _suffixed(lemma, ("sen", "sens", "sarna", "sarnas"))
    ):
        return (
            SALDO_ZERO_AND_S_PLURAL_DEFINITE_PARADIGM,
            "SAOL explicitly allows both zero plural and -s plural and supplies definite forms for both; SALDO follows the -s branch with exactly the competing -sen/-sens and -sarna/-sarnas continuations",
        )

    # SAOL has zero plural with -na/-nas definite plural, while SALDO instead
    # has a complete -s definite paradigm.
    if (
        notation == "+n; pl. +"
        and extra == _suffixed(lemma, ("na", "nas"))
        and missing == _suffixed(lemma, ("sen", "sens", "sarna", "sarnas"))
    ):
        return (
            SALDO_ZERO_VS_S_PLURAL_DEFINITE_PARADIGM,
            "SAOL explicitly has zero plural with -na/-nas definite plural while SALDO instead supplies exactly the competing -s definite-singular/plural paradigm",
        )

    # SAOL explicitly supplies an alternative regular plural that SALDO lacks,
    # while all other generated forms agree.
    alternative_plural_patterns = {
        "+et; pl. + el. +er": ("er", "ers", "erna", "ernas"),
        "+en; pl. +ar el. +er": ("er", "ers", "erna", "ernas"),
    }
    alternative_plural = alternative_plural_patterns.get(notation)
    if alternative_plural is not None and not missing and extra == _suffixed(lemma, alternative_plural):
        return (
            SALDO_MISSING_ALTERNATIVE_PLURAL,
            f"SAOL notation {notation} explicitly supplies an alternative regular plural paradigm that SALDO lacks exactly",
        )

    # SAOL permits zero plural alongside a regular plural; SALDO covers the
    # regular branch but lacks only the definite zero-plural forms.
    if (
        notation == "+en; pl. + el. +ar"
        and not missing
        and extra == _suffixed(lemma, ("na", "nas"))
    ):
        return (
            SALDO_MISSING_ZERO_PLURAL_DEFINITE,
            "SAOL explicitly permits zero plural alongside -ar plural and supplies -na/-nas for the zero-plural branch; SALDO lacks exactly those definite zero-plural forms",
        )

    # SAOL has common and neuter definite-singular alternatives while SALDO
    # covers the common-gender branch and lacks only -et/-ets.
    alternative_neuter_notations = {
        "+en el. +et; pl. +ar el. +",
        "+en el. +et; pl. +er el. +",
    }
    if (
        notation in alternative_neuter_notations
        and not missing
        and extra == _suffixed(lemma, ("et", "ets"))
    ):
        return (
            SALDO_MISSING_ALTERNATIVE_NEUTER_DEFINITE_SINGULAR,
            "SAOL explicitly supplies an alternative neuter definite-singular pair -et/-ets while SALDO covers the other branch and lacks exactly this alternative",
        )

    # Exact common-gender/neuter definite-singular swap with no other difference.
    if notation == "+et" and extra == _suffixed(lemma, ("et", "ets")) and missing == _suffixed(lemma, ("en", "ens")):
        return (
            SALDO_COMPETING_DEFINITE_SINGULAR_GENDER,
            "SAOL has exactly neuter definite singular -et/-ets while SALDO has exactly common-gender -en/-ens",
        )
    if notation == "+en" and extra == _suffixed(lemma, ("en", "ens")) and missing == _suffixed(lemma, ("et", "ets")):
        return (
            SALDO_COMPETING_DEFINITE_SINGULAR_GENDER,
            "SAOL has exactly common-gender definite singular -en/-ens while SALDO has exactly neuter -et/-ets",
        )

    # Exact -en/-n definite-singular allomorph swap while the plural paradigm agrees.
    if notation == "+en +er" and extra == _suffixed(lemma, ("en", "ens")) and missing == _suffixed(lemma, ("n", "ns")):
        return (
            SALDO_COMPETING_DEFINITE_SINGULAR_ALLOMORPH,
            "SAOL has exactly definite singular -en/-ens while SALDO has exactly the competing -n/-ns allomorph",
        )

    return UNCLASSIFIED, "no_batch_pattern"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def classify_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in rows:
        classification, rationale = classify_batch_row(row)
        if classification == UNCLASSIFIED:
            continue
        result.append({
            **row,
            "batch_classification": classification,
            "batch_rationale": rationale,
        })
    return result


def build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(str(row["batch_classification"]) for row in rows)
    notation_counts = Counter(str(row.get("notation", "")) for row in rows)
    examples: dict[str, list[str]] = {}
    for classification in counts:
        examples[classification] = [
            str(row.get("lemma", ""))
            for row in rows
            if row["batch_classification"] == classification
        ][:20]
    return {
        "records": len(rows),
        "classification_counts": dict(sorted(counts.items(), key=lambda item: (-item[1], item[0]))),
        "notation_counts": dict(sorted(notation_counts.items(), key=lambda item: (-item[1], item[0]))),
        "examples": examples,
    }


def render_text(summary: dict[str, Any]) -> str:
    lines = ["SAOL14 nästa NOUN-batch", "", f"Träffar totalt: {summary['records']}", "", "Klassningar:"]
    for name, count in summary["classification_counts"].items():
        lines.append(f"{count:5}  {name}")
        lines.append("       Exempel: " + ", ".join(summary["examples"].get(name, [])))
    lines.extend(["", "Notationer:"])
    for notation, count in summary["notation_counts"].items():
        lines.append(f"{count:5}  {notation or '(null)'}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch-audit av flera mekaniskt säkra oklassificerade NOUN-familjer")
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    args = parser.parse_args()

    rows = classify_rows(read_jsonl(args.input))
    summary = build_summary(rows)
    args.jsonl.parent.mkdir(parents=True, exist_ok=True)
    with args.jsonl.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.text.write_text(render_text(summary), encoding="utf-8")

    print(f"Träffar totalt: {summary['records']}")
    for name, count in summary["classification_counts"].items():
        print(f"{name}: {count}")
    print(f"Text: {args.text}")
    print(f"JSONL: {args.jsonl}")


if __name__ == "__main__":
    main()
