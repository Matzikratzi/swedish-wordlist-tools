from __future__ import annotations

import argparse
import hashlib
import json
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .artifact_paths import SAOL14_GAMEWORDS
from .jsonl import read_jsonl


DEFAULT_INPUT = Path("reports/saol14-shared-wordlist.jsonl")
DEFAULT_OUTPUT = SAOL14_GAMEWORDS
DEFAULT_JSONL = Path("reports/saol14-gamewords.jsonl")
DEFAULT_REJECTED = Path("reports/saol14-gamewords-rejected.jsonl")
DEFAULT_SUMMARY = Path("reports/saol14-gamewords-summary.json")


def normalise_game_word(value: str) -> str:
    return unicodedata.normalize("NFC", value.strip()).casefold()


def rejection_reason(word: str) -> str | None:
    if not word:
        return "EMPTY"
    if len(word) < 2:
        return "ONE_CHARACTER"
    if word.isalpha():
        return None
    if any(character.isdigit() for character in word):
        return "CONTAINS_DIGIT"
    if "-" in word:
        return "CONTAINS_HYPHEN"
    if "'" in word or "’" in word:
        return "CONTAINS_APOSTROPHE"
    return "CONTAINS_OTHER_NONLETTER"


def _strings(row: dict[str, Any], key: str) -> set[str]:
    values = row.get(key, ())
    if isinstance(values, str):
        return {values} if values else set()
    return {str(value) for value in values if str(value)}


def build_rows(
    source_rows: Iterable[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    accepted: dict[str, dict[str, Any]] = {}
    rejected: list[dict[str, Any]] = []
    rejection_counts: Counter[str] = Counter()
    source_count = 0
    duplicates = 0

    for source_row in source_rows:
        source_count += 1
        original = str(source_row.get("form") or "")
        word = normalise_game_word(original)
        reason = rejection_reason(word)
        if reason is not None:
            rejection_counts[reason] += 1
            rejected.append({
                "form": original,
                "normalised_form": word,
                "reason": reason,
                "classification": source_row.get("classification"),
                "upos": sorted(_strings(source_row, "upos")),
                "source_record_ids": sorted(_strings(source_row, "source_record_ids")),
                "provenance": sorted(_strings(source_row, "provenance")),
            })
            continue

        existing = accepted.get(word)
        if existing is None:
            accepted[word] = {
                "form": word,
                "source_forms": {original} - {""},
                "classifications": _strings(source_row, "classification"),
                "upos": _strings(source_row, "upos"),
                "source_record_ids": _strings(source_row, "source_record_ids"),
                "provenance": _strings(source_row, "provenance"),
            }
            continue

        duplicates += 1
        existing["source_forms"].update({original} - {""})
        existing["classifications"].update(_strings(source_row, "classification"))
        existing["upos"].update(_strings(source_row, "upos"))
        existing["source_record_ids"].update(_strings(source_row, "source_record_ids"))
        existing["provenance"].update(_strings(source_row, "provenance"))

    rows = [
        {
            "form": row["form"],
            "source_forms": sorted(row["source_forms"], key=str.casefold),
            "classifications": sorted(row["classifications"]),
            "upos": sorted(row["upos"]),
            "source_record_ids": sorted(row["source_record_ids"]),
            "provenance": sorted(row["provenance"]),
        }
        for row in accepted.values()
    ]
    rows.sort(key=lambda row: str(row["form"]))
    rejected.sort(key=lambda row: (normalise_game_word(str(row["form"])), str(row["form"])))
    summary = {
        "authority": "SAOL14",
        "saldo_affects_output": False,
        "source_rows": source_count,
        "game_words": len(rows),
        "rejected_rows": len(rejected),
        "rejections_by_reason": dict(sorted(rejection_counts.items())),
        "duplicates_after_nfc_casefold": duplicates,
        "normalisation": ["Unicode NFC", "casefold", "minimum length 2", "letters only"],
    }
    return rows, rejected, summary


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_final_wordlist(
    input_path: Path = DEFAULT_INPUT,
    output_path: Path = DEFAULT_OUTPUT,
    jsonl_path: Path = DEFAULT_JSONL,
    rejected_path: Path = DEFAULT_REJECTED,
    summary_path: Path = DEFAULT_SUMMARY,
) -> dict[str, Any]:
    rows, rejected, summary = build_rows(read_jsonl(input_path))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "\n".join(str(row["form"]) for row in rows) + ("\n" if rows else ""),
        encoding="utf-8",
    )
    _write_jsonl(jsonl_path, rows)
    _write_jsonl(rejected_path, rejected)

    report = {
        "source": str(input_path),
        "source_sha256": _sha256(input_path),
        "output": str(output_path),
        "output_sha256": _sha256(output_path),
        "jsonl": str(jsonl_path),
        "rejected": str(rejected_path),
        **summary,
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build the canonical SAOL14-only game wordlist. SALDO is deliberately "
            "not read by this command and cannot affect its output."
        )
    )
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--rejected", type=Path, default=DEFAULT_REJECTED)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = build_final_wordlist(
        args.input, args.output, args.jsonl, args.rejected, args.summary
    )
    print(f"SAOL14-källrader: {report['source_rows']}")
    print(f"Spelord: {report['game_words']}")
    print(f"Bortfiltrerade rader: {report['rejected_rows']}")
    print(f"Dubletter efter NFC/casefold: {report['duplicates_after_nfc_casefold']}")
    print(f"Spelordlista: {report['output']}")
    print(f"Rapport: {args.summary}")


if __name__ == "__main__":
    main()
