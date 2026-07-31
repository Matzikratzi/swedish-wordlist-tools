from __future__ import annotations

import argparse
import json
import unicodedata
from pathlib import Path
from typing import Iterable

from .saldo import read_saldo_analyses

DEFAULT_INPUT = Path("data/processed/saol14-saldo-forms.txt")
DEFAULT_SALDO = Path("data/raw/saldom.xml")
DEFAULT_OUTPUT = Path("data/processed/saol14-game-words.txt")
DEFAULT_REPORT = Path("reports/saol14-game-words.json")


def normalise_game_word(value: str) -> str | None:
    word = unicodedata.normalize("NFC", value.strip()).casefold()
    if not word or len(word) < 2 or not word.isalpha():
        return None
    return word


def standalone_saldo_forms(path: Path) -> set[str]:
    result: set[str] = set()
    for analyses in read_saldo_analyses(path).values():
        for analysis in analyses:
            result.update(analysis.lemmas)
            for form in analysis.word_forms:
                if str(form.msd).casefold() not in {"ci", "cm", "sms"}:
                    result.add(form.written_form)
    return result


def filter_game_words(
    forms: Iterable[str], allowed_forms: set[str] | None = None
) -> tuple[list[str], dict[str, int]]:
    words: list[str] = []
    seen: set[str] = set()
    source_forms = 0
    rejected_forms = 0
    rejected_non_standalone = 0
    duplicate_forms = 0
    allowed = None
    if allowed_forms is not None:
        allowed = set()
        for value in allowed_forms:
            word = normalise_game_word(value)
            if word is not None:
                allowed.add(word)

    for raw in forms:
        source_forms += 1
        word = normalise_game_word(raw)
        if word is None:
            rejected_forms += 1
            continue
        if allowed is not None and word not in allowed:
            rejected_non_standalone += 1
            continue
        if word in seen:
            duplicate_forms += 1
            continue
        seen.add(word)
        words.append(word)

    words.sort()
    return words, {
        "source_forms": source_forms,
        "rejected_non_playable_forms": rejected_forms,
        "rejected_non_standalone_saldo_forms": rejected_non_standalone,
        "duplicate_after_normalisation": duplicate_forms,
        "game_words": len(words),
    }


def build_game_wordlist(
    input_path: Path = DEFAULT_INPUT,
    saldo_path: Path = DEFAULT_SALDO,
    output_path: Path = DEFAULT_OUTPUT,
    report_path: Path = DEFAULT_REPORT,
) -> dict[str, object]:
    allowed_forms = standalone_saldo_forms(saldo_path)
    source_lines = input_path.read_text(encoding="utf-8").splitlines()
    words, counts = filter_game_words(source_lines, allowed_forms)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(words) + ("\n" if words else ""), encoding="utf-8")
    report: dict[str, object] = {
        "source": str(input_path),
        "saldo": str(saldo_path),
        "output": str(output_path),
        **counts,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a tile-game wordlist from verified SAOL/SALDO forms")
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--saldo", type=Path, default=DEFAULT_SALDO)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = build_game_wordlist(args.input, args.saldo, args.output, args.report)
    print(f"Verifierade SALDO-former: {report['source_forms']}")
    print(f"Bortfiltrerade icke spelbara former: {report['rejected_non_playable_forms']}")
    print(f"Bortfiltrerade sammansättnings-/citatvarianter: {report['rejected_non_standalone_saldo_forms']}")
    print(f"Dubletter efter gemener/normalisering: {report['duplicate_after_normalisation']}")
    print(f"Ord i spelordlistan: {report['game_words']}")
    print(f"Spelordlista: {report['output']}")
    print(f"Rapport: {args.report}")


if __name__ == "__main__":
    main()
