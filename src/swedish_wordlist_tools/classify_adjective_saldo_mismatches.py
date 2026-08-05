from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

DEFAULT_INPUT = Path("reports/saol14-adjective-slots-saldo.jsonl")
DEFAULT_TEXT = Path("reports/saol14-adjective-mismatch-causes.txt")
DEFAULT_JSON = Path("reports/saol14-adjective-mismatch-causes.json")
DEFAULT_JSONL = Path("reports/saol14-adjective-mismatch-causes.jsonl")

_WORD = re.compile(r"[a-zåäöéü]+", re.IGNORECASE)
_OPERATION = re.compile(r"[+-]?[a-zåäöéü]+", re.IGNORECASE)


def _tokens(notation: str) -> tuple[str, ...]:
    return tuple(_OPERATION.findall(notation.casefold()))


def _operation_kind(token: str) -> str:
    if token.startswith("-"):
        return "replace_tail"
    if token.startswith("+"):
        return "append"
    return "explicit"


def _slot_operation_token(slot: str, notation: str) -> str | None:
    """Find the operation token that most directly supplies one adjective slot.

    This deliberately handles the common SAOL layouts rather than assigning every
    generated form the same derivation merely because the notation contains '-'.
    """

    normalized = " ".join(notation.casefold().split())

    # The overwhelmingly common positive pattern has neuter first and
    # definite/plural second: '-fött +a', '+t +a', 'litet små'.
    first_branch = normalized.split(" _ ", 1)[0]
    lexical = [token for token in _tokens(first_branch) if token not in {"pl", "n", "best", "mask", "komp", "superl"}]

    if slot == "neuter_singular" and lexical:
        return lexical[0]
    if slot == "definite_or_plural" and len(lexical) >= 2:
        return lexical[1]

    # Labelled one-form patterns such as 'pl. -a'.
    if slot == "definite_or_plural" and normalized.startswith(("pl. ", "best. ")) and lexical:
        return lexical[-1]

    if slot == "comparative":
        match = re.search(r"komp\.\s+([+-]?[a-zåäöéü]+)", normalized)
        return match.group(1) if match else None
    if slot == "superlative":
        match = re.search(r"superl\.\s+([+-]?[a-zåäöéü]+)", normalized)
        return match.group(1) if match else None
    return None


def _form_derivation(form: str, lemma: str, notation: str, slot: str) -> str:
    tokens = _tokens(notation)
    if form == lemma:
        return "lemma"
    if form in {token for token in tokens if not token.startswith(("+", "-"))}:
        return "explicit"

    token = _slot_operation_token(slot, notation)
    if token:
        return _operation_kind(token)

    if any(token.startswith("+") for token in tokens):
        return "append"
    if any(token.startswith("-") and len(token) > 1 for token in tokens):
        return "replace_tail"
    return "unknown_derivation"


def _common_prefix_length(left: str, right: str) -> int:
    count = 0
    for a, b in zip(left.casefold(), right.casefold()):
        if a != b:
            break
        count += 1
    return count


def _looks_like_lost_prefix(form: str, lemma: str, derivation: str) -> bool:
    """Flag replace-tail output that has implausibly discarded the lemma prefix."""

    return (
        derivation == "replace_tail"
        and len(form) < len(lemma)
        and _common_prefix_length(form, lemma) < 2
    )


def classify_row(row: dict[str, Any]) -> dict[str, Any] | None:
    missing = list(row.get("missing_forms") or ())
    if not missing:
        return None
    lemma = str(row.get("lemma") or "")
    notation = str(row.get("effective_notation") or row.get("notation") or "")
    classified = []
    for form in missing:
        written = str(form.get("written_form") or "")
        slot = str(form.get("slot") or "")
        derivation = _form_derivation(written, lemma, notation, slot)
        lost_prefix = _looks_like_lost_prefix(written, lemma, derivation)
        if row.get("source_correction_applied"):
            cause = "suspected_saol_error_corrected"
        elif lost_prefix:
            cause = "possible_lost_prefix"
        elif derivation == "explicit":
            cause = "saldo_coverage_difference"
        elif derivation == "lemma":
            cause = "saldo_alignment_problem"
        elif derivation in {"append", "replace_tail"}:
            cause = "needs_parser_or_saldo_review"
        else:
            cause = "unresolved"
        classified.append({
            **form,
            "derivation": derivation,
            "preliminary_cause": cause,
            "possible_lost_prefix": lost_prefix,
        })
    return {**row, "classified_missing_forms": classified}


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def build_report(path: Path = DEFAULT_INPUT) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows = [classified for row in read_jsonl(path) if (classified := classify_row(row))]
    cause_counts = Counter(
        form["preliminary_cause"]
        for row in rows
        for form in row["classified_missing_forms"]
    )
    derivation_counts = Counter(
        form["derivation"]
        for row in rows
        for form in row["classified_missing_forms"]
    )
    examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        for form in row["classified_missing_forms"]:
            cause = form["preliminary_cause"]
            if len(examples[cause]) < 30:
                examples[cause].append({
                    "lemma": row.get("lemma"),
                    "notation": row.get("effective_notation") or row.get("notation"),
                    "slot": form.get("slot"),
                    "form": form.get("written_form"),
                    "derivation": form.get("derivation"),
                    "saldo_forms": row.get("saldo_forms", []),
                })
    report = {
        "rows_with_missing_forms": len(rows),
        "missing_forms": sum(cause_counts.values()),
        "cause_counts": dict(cause_counts.most_common()),
        "derivation_counts": dict(derivation_counts.most_common()),
        "examples": dict(examples),
        "note": (
            "These are preliminary triage categories. Explicit SAOL forms normally point to "
            "SALDO coverage differences. Generated forms that appear to lose the lemma prefix "
            "are isolated before the remaining append/replace forms are reviewed against SAOL "
            "notation, implementation, SALDO alignment and source extraction."
        ),
    }
    return report, rows


def render_text(report: dict[str, Any]) -> str:
    lines = [
        f"Rader med saknade former: {report['rows_with_missing_forms']}",
        f"Saknade former: {report['missing_forms']}",
        "",
        "Preliminär orsak:",
    ]
    for cause, count in report["cause_counts"].items():
        lines.append(f"  {count:6d}  {cause}")
    lines.extend(["", "Härledning:"])
    for derivation, count in report["derivation_counts"].items():
        lines.append(f"  {count:6d}  {derivation}")
    for cause, examples in report.get("examples", {}).items():
        lines.extend(["", f"Exempel: {cause}"])
        for item in examples[:20]:
            lines.append(
                f"  {item['lemma']} | {item['notation']} | "
                f"{item['slot']}={item['form']} | {item['derivation']}"
            )
    return "\n".join(lines) + "\n"


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Classify remaining adjective SALDO mismatches")
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report, rows = build_report(args.input)
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render_text(report), encoding="utf-8")
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_jsonl(args.jsonl, rows)
    print(f"Rader med saknade former: {report['rows_with_missing_forms']}")
    print(f"Saknade former: {report['missing_forms']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")
    print(f"JSONL: {args.jsonl}")


if __name__ == "__main__":
    main()
