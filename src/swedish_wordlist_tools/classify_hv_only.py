from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .analyze_x_routing import _is_hv, _primary_text
from .audit_ignore_hv import analyze as audit_ignore_hv
from .jsonl import read_jsonl
from .saol_surface import clean_saol_word

DEFAULT_SOURCE = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_TEXT = Path("reports/saol14-hv-only-classification.txt")
DEFAULT_JSON = Path("reports/saol14-hv-only-classification.json")

UNKNOWN_WORD = "UNKNOWN_WORD"
CONTEXT_ONLY = "CONTEXT_ONLY"

LIKELY_TRUNCATED_EXPORT = "LIKELY_TRUNCATED_EXPORT"
LIKELY_UNEXPORTED_ARTICLE_CONTEXT = "LIKELY_UNEXPORTED_ARTICLE_CONTEXT"
NO_EXPORTED_TARGET_ROW = "NO_EXPORTED_TARGET_ROW"
MULTIWORD_CONTEXT = "MULTIWORD_CONTEXT"

_TRUNCATION_LENGTH = 49


def _words(value: str) -> list[str]:
    return [part for part in re.split(r"[^0-9A-Za-zÅÄÖåäöÉéÜü]+", value.casefold()) if part]


def classify_case(case: dict[str, Any]) -> tuple[str, str]:
    """Classify one form that survives only through an (hv) row.

    We deliberately do not infer a word class.  A form is CONTEXT_ONLY only
    when the export itself gives strong structural evidence that it belongs to
    a multiword expression: either the printed form is multiword, or it is a
    strict token/subphrase of the multiword normalized expression.  Everything
    else is retained as an UNKNOWN_WORD and is not inflected further.
    """

    form = str(case.get("form") or "").strip()
    lemma = str(case.get("hv_lemma") or "").strip()
    if not form:
        return CONTEXT_ONLY, "empty_form"

    if re.search(r"\s", form):
        return CONTEXT_ONLY, "printed_form_is_multiword"

    lemma_words = _words(lemma)
    form_words = _words(form)
    if len(lemma_words) > 1 and form_words:
        n = len(form_words)
        for start in range(len(lemma_words) - n + 1):
            if lemma_words[start : start + n] == form_words:
                return CONTEXT_ONLY, "strict_part_of_multiword_lemma"

    return UNKNOWN_WORD, "standalone_hv_only_form"


def _key(value: Any) -> str:
    return clean_saol_word(value).casefold().strip()


def _target_rows_by_lemma(records: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if _is_hv(record):
            continue
        lemma = _key(record.get("normaliserat_ord"))
        if lemma:
            result[lemma].append(record)
    return result


def diagnose_export_gap(
    case: dict[str, Any],
    target_rows_by_lemma: dict[str, list[dict[str, Any]]],
    classification: str,
) -> tuple[str, list[dict[str, Any]]]:
    """Estimate why an hv-only form is absent from exported real-row evidence.

    This is deliberately evidence-based and non-destructive.  A 49+ character
    real-row text is treated as a truncation candidate because SAOL14 export
    examples have repeatedly shown a hard boundary around 49-50 characters.
    Otherwise a surviving standalone hv form is labelled as likely coming from
    article/example context that the JSONL export does not expose.  The label is
    a hypothesis, not a claim about the unseen facsimile text.
    """

    if classification == CONTEXT_ONLY:
        return MULTIWORD_CONTEXT, []

    lemma = _key(case.get("hv_lemma"))
    target_rows = target_rows_by_lemma.get(lemma, [])
    evidence: list[dict[str, Any]] = []
    truncated = False
    for record in target_rows:
        text = _primary_text(record)
        text_len = len(text) if text else 0
        if text_len >= _TRUNCATION_LENGTH:
            truncated = True
        evidence.append({
            "record_id": str(record.get("id") or record.get("subnr") or record.get("urspr_lopnr") or ""),
            "ord": clean_saol_word(record.get("ord")),
            "homonr": str(record.get("homonr") or ""),
            "ordkl": str(record.get("ordkl") or ""),
            "text": text,
            "text_length": text_len,
            "truncation_candidate": text_len >= _TRUNCATION_LENGTH,
        })

    if truncated:
        return LIKELY_TRUNCATED_EXPORT, evidence
    if target_rows:
        return LIKELY_UNEXPORTED_ARTICLE_CONTEXT, evidence
    return NO_EXPORTED_TARGET_ROW, evidence


def analyze(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    materialized = [dict(record) for record in records]
    audit = audit_ignore_hv(materialized)
    target_rows_by_lemma = _target_rows_by_lemma(materialized)
    rows: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    gap_counts: Counter[str] = Counter()
    seen: set[tuple[str, str]] = set()

    for case in audit["cases"]:
        if case.get("status") != "hv_only":
            continue
        classification, reason = classify_case(case)
        key = (str(case.get("form") or "").casefold(), classification)
        if key in seen:
            continue
        seen.add(key)
        gap_hypothesis, target_evidence = diagnose_export_gap(
            case, target_rows_by_lemma, classification
        )
        counts[classification] += 1
        reason_counts[reason] += 1
        gap_counts[gap_hypothesis] += 1
        rows.append({
            "form": case.get("form"),
            "classification": classification,
            "reason": reason,
            "gap_hypothesis": gap_hypothesis,
            "target_evidence": target_evidence,
            "upos": "X" if classification == UNKNOWN_WORD else None,
            "generate_inflections": False,
            "hv_lemma": case.get("hv_lemma"),
            "hv_homonr": case.get("hv_homonr"),
            "hv_record_id": case.get("hv_record_id"),
        })

    rows.sort(key=lambda row: (row["classification"], str(row["form"]).casefold()))
    return {
        "hv_only_unique_forms": len(rows),
        "classification_counts": dict(sorted(counts.items())),
        "reason_counts": dict(sorted(reason_counts.items())),
        "gap_hypothesis_counts": dict(sorted(gap_counts.items())),
        "rows": rows,
    }


def render_text(report: dict[str, Any]) -> str:
    lines = [
        "SAOL14: klassificering av former som bara återstår via (hv)",
        "",
        "UNKNOWN_WORD = SAOL belägger själva formen men exporten räcker inte för",
        "att fastställa ordklass/sammanhang. Formen tas med som den står, UPOS=X,",
        "och inga ytterligare böjningar genereras.",
        "CONTEXT_ONLY = stark strukturell signal att formen är hela eller del av",
        "ett flerordsuttryck; den tas inte med som fristående ord.",
        "",
        "Gap-hypoteserna är diagnostiska, inte säkra fakta:",
        "  LIKELY_TRUNCATED_EXPORT = mållemmat har exporterad text på minst 49 tecken.",
        "  LIKELY_UNEXPORTED_ARTICLE_CONTEXT = mållemmat finns men exporttexten ger",
        "    ingen trunceringssignal; formen kan ligga i exempel-/artikeltext som inte exporteras.",
        "  NO_EXPORTED_TARGET_ROW = ingen icke-hv-rad för mållemmat hittades.",
        "  MULTIWORD_CONTEXT = formen är strukturellt knuten till flerordsuttryck.",
        "",
        f"Unika hv_only-former: {report['hv_only_unique_forms']}",
        "Klassificering:",
    ]
    for key, count in report["classification_counts"].items():
        lines.append(f"  {count:4d}  {key}")
    lines.append("Orsaker:")
    for key, count in report["reason_counts"].items():
        lines.append(f"  {count:4d}  {key}")
    lines.append("Gap-hypotes:")
    for key, count in report["gap_hypothesis_counts"].items():
        lines.append(f"  {count:4d}  {key}")

    for classification in (UNKNOWN_WORD, CONTEXT_ONLY):
        matching = [row for row in report["rows"] if row["classification"] == classification]
        lines.extend(["", "=" * 78, f"{classification}: {len(matching)}"])
        for row in matching:
            evidence = "; ".join(
                f"{item['ord']}({item['homonr']}) len={item['text_length']} text={item['text']!r}"
                for item in row["target_evidence"][:3]
            ) or "-"
            lines.append(
                f"  {row['form']!r} <- hv {row['hv_lemma']}({row['hv_homonr']}) | "
                f"{row['reason']} | {row['gap_hypothesis']} | target={evidence}"
            )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify SAOL forms that survive only through (hv) rows")
    parser.add_argument("source", nargs="?", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()

    report = analyze(read_jsonl(args.source))
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render_text(report), encoding="utf-8")
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"hv_only-former: {report['hv_only_unique_forms']}")
    for key, count in report["classification_counts"].items():
        print(f"{key}: {count}")
    for key, count in report["gap_hypothesis_counts"].items():
        print(f"{key}: {count}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
