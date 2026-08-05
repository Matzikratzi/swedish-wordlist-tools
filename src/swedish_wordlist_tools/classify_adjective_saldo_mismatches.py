from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .replay_adjective_form import replay_generated_form

DEFAULT_INPUT = Path("reports/saol14-adjective-slots-saldo.jsonl")
DEFAULT_TEXT = Path("reports/saol14-adjective-mismatch-causes.txt")
DEFAULT_JSON = Path("reports/saol14-adjective-mismatch-causes.json")
DEFAULT_JSONL = Path("reports/saol14-adjective-mismatch-causes.jsonl")


def classify_row(row: dict[str, Any]) -> dict[str, Any] | None:
    missing = list(row.get("missing_forms") or ())
    if not missing:
        return None

    notation = str(row.get("effective_notation") or row.get("notation") or "")
    classified = []
    for form in missing:
        derivation = str(form.get("provenance") or "unknown")
        source_token = str(form.get("source_token") or "")
        replay = replay_generated_form(
            lemma=str(row.get("lemma") or ""),
            stycke=str(row.get("stycke") or ""),
            written_form=str(form.get("written_form") or ""),
            slot=str(form.get("slot") or ""),
            provenance=derivation,
            source_token=source_token,
            notation=notation,
        )
        if row.get("source_correction_applied"):
            cause = "suspected_saol_error"
        elif derivation == "lemma":
            cause = "needs_saldo_alignment_review"
        elif replay.status == "mismatch":
            cause = "needs_parser_review"
        elif derivation == "explicit":
            cause = "needs_saldo_review"
        elif replay.status == "match":
            cause = "generation_consistent_review_saldo_or_saol"
        else:
            cause = "needs_manual_review"
        classified.append({
            **form,
            "derivation": derivation,
            "source_token": source_token,
            "replay_status": replay.status,
            "replayed_form": replay.replayed_form or "",
            "preliminary_cause": cause,
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
    replay_counts = Counter(
        form["replay_status"]
        for row in rows
        for form in row["classified_missing_forms"]
    )
    source_token_counts = Counter(
        form["source_token"]
        for row in rows
        for form in row["classified_missing_forms"]
        if form.get("source_token")
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
                    "source_token": form.get("source_token"),
                    "replay_status": form.get("replay_status"),
                    "replayed_form": form.get("replayed_form"),
                    "saldo_forms": row.get("saldo_forms", []),
                })
    report = {
        "rows_with_missing_forms": len(rows),
        "missing_forms": sum(cause_counts.values()),
        "cause_counts": dict(cause_counts.most_common()),
        "derivation_counts": dict(derivation_counts.most_common()),
        "replay_counts": dict(replay_counts.most_common()),
        "source_token_counts": dict(source_token_counts.most_common()),
        "examples": dict(examples),
        "note": (
            "The replay check applies the stored primitive source token to lemma/stycke. "
            "A documented lodstreck takes precedence over overlap fallback. Parallel "
            "alternative paradigms are unsupported because their active base may not be "
            "the entry lemma. A match confirms consistency, not whether SALDO or SAOL is right."
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
    lines.extend(["", "Återspelning av lagrad operation:"])
    for status, count in report["replay_counts"].items():
        lines.append(f"  {count:6d}  {status}")
    lines.extend(["", "Härledning:"])
    for derivation, count in report["derivation_counts"].items():
        lines.append(f"  {count:6d}  {derivation}")
    lines.extend(["", "Vanligaste SAOL-token för saknade former:"])
    for token, count in list(report.get("source_token_counts", {}).items())[:30]:
        lines.append(f"  {count:6d}  {token}")
    for cause, examples in report.get("examples", {}).items():
        lines.extend(["", f"Exempel: {cause}"])
        for item in examples[:20]:
            token = f" | token={item['source_token']}" if item.get("source_token") else ""
            replay = f" | replay={item['replay_status']}"
            if item.get("replayed_form"):
                replay += f":{item['replayed_form']}"
            lines.append(
                f"  {item['lemma']} | {item['notation']} | "
                f"{item['slot']}={item['form']} | {item['derivation']}{token}{replay}"
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
