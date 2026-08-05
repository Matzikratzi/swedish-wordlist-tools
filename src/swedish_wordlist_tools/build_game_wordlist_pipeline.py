from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Callable, Sequence


DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_ADJECTIVES = Path("reports/saol14-adjective-forms.jsonl")
DEFAULT_ADJECTIVE_SUMMARY = Path("reports/saol14-adjective-forms-summary.json")
DEFAULT_INPUT = Path("data/processed/saol14-saldo-forms.txt")
DEFAULT_SALDO = Path("data/raw/saldom.xml")
DEFAULT_OUTPUT = Path("data/processed/saol14-game-words.txt")
DEFAULT_GAME_REPORT = Path("reports/saol14-game-words.json")
DEFAULT_AUDIT_TEXT = Path("reports/saol14-game-adjective-integration-audit.txt")
DEFAULT_AUDIT_JSON = Path("reports/saol14-game-adjective-integration-audit.json")
DEFAULT_ADDED_WORDS = Path("reports/saol14-game-adjective-added-words.txt")

Runner = Callable[[Sequence[str]], None]


def subprocess_runner(command: Sequence[str]) -> None:
    subprocess.run(list(command), check=True)


def pipeline_commands(args: argparse.Namespace) -> list[list[str]]:
    python = sys.executable
    return [
        [
            python,
            "-m",
            "swedish_wordlist_tools.generate_adjective_forms",
            str(args.saol),
            "--jsonl",
            str(args.adjective_forms),
            "--summary",
            str(args.adjective_summary),
        ],
        [
            python,
            "-m",
            "swedish_wordlist_tools.game_wordlist",
            str(args.input),
            "--saldo",
            str(args.saldo),
            "--adjective-forms",
            str(args.adjective_forms),
            "--output",
            str(args.output),
            "--report",
            str(args.game_report),
        ],
        [
            python,
            "-m",
            "swedish_wordlist_tools.audit_game_adjective_integration",
            "--input",
            str(args.input),
            "--saldo",
            str(args.saldo),
            "--adjective-forms",
            str(args.adjective_forms),
            "--final-adjudication",
            str(args.final_adjudication),
            "--text",
            str(args.audit_text),
            "--json",
            str(args.audit_json),
            "--added-words",
            str(args.added_words),
        ],
    ]


def run_pipeline(args: argparse.Namespace, runner: Runner = subprocess_runner) -> None:
    for command in pipeline_commands(args):
        runner(command)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build the canonical adjective artifact, export the game wordlist, and "
            "fail if the adjective integration audit is not clean"
        )
    )
    parser.add_argument("--saol", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--saldo", type=Path, default=DEFAULT_SALDO)
    parser.add_argument("--adjective-forms", type=Path, default=DEFAULT_ADJECTIVES)
    parser.add_argument("--adjective-summary", type=Path, default=DEFAULT_ADJECTIVE_SUMMARY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--game-report", type=Path, default=DEFAULT_GAME_REPORT)
    parser.add_argument(
        "--final-adjudication",
        type=Path,
        default=Path("reports/saol14-adjective-final-adjudication.jsonl"),
    )
    parser.add_argument("--audit-text", type=Path, default=DEFAULT_AUDIT_TEXT)
    parser.add_argument("--audit-json", type=Path, default=DEFAULT_AUDIT_JSON)
    parser.add_argument("--added-words", type=Path, default=DEFAULT_ADDED_WORDS)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_pipeline(args)
    print("Spelordlistebygge klart och integrationsrevisionen är ren.")
    print(f"Spelordlista: {args.output}")
    print(f"Revisionsrapport: {args.audit_text}")


if __name__ == "__main__":
    main()
