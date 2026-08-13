from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Callable, Sequence

from .artifact_paths import SAOL14_GAMEWORDS
from .audit_final_wordlist_saldo import (
    DEFAULT_CANDIDATES,
    DEFAULT_JSON as DEFAULT_AUDIT_JSON,
    DEFAULT_ONLY_SALDO,
    DEFAULT_ONLY_SAOL,
    DEFAULT_SALDO,
    DEFAULT_TEXT as DEFAULT_AUDIT_TEXT,
)
from .build_final_wordlist import (
    DEFAULT_JSONL as DEFAULT_GAMEWORDS_JSONL,
    DEFAULT_REJECTED,
    DEFAULT_SUMMARY as DEFAULT_GAMEWORDS_SUMMARY,
)
from .build_shared_wordlist import (
    DEFAULT_JSONL as DEFAULT_SHARED_JSONL,
    DEFAULT_SOURCE as DEFAULT_SAOL,
    DEFAULT_SUMMARY as DEFAULT_SHARED_SUMMARY,
    DEFAULT_WORDS as DEFAULT_SHARED_WORDS,
)


Runner = Callable[[Sequence[str]], None]
DEFAULT_OUTPUT = SAOL14_GAMEWORDS


def subprocess_runner(command: Sequence[str]) -> None:
    subprocess.run(list(command), check=True)


def pipeline_commands(args: argparse.Namespace) -> list[list[str]]:
    python = sys.executable
    return [
        [
            python, "-m", "swedish_wordlist_tools.build_shared_wordlist",
            str(args.saol), "--words", str(args.shared_words),
            "--jsonl", str(args.shared_jsonl), "--summary", str(args.shared_summary),
        ],
        [
            python, "-m", "swedish_wordlist_tools.build_final_wordlist",
            str(args.shared_jsonl), "--output", str(args.output),
            "--jsonl", str(args.gamewords_jsonl), "--rejected", str(args.rejected),
            "--summary", str(args.gamewords_summary),
        ],
        [
            python, "-m", "swedish_wordlist_tools.audit_final_wordlist_saldo",
            "--gamewords", str(args.output), "--saol", str(args.saol),
            "--saldo", str(args.saldo), "--text", str(args.audit_text),
            "--json", str(args.audit_json), "--only-saol", str(args.only_saol),
            "--only-saldo", str(args.only_saldo), "--candidates", str(args.candidates),
        ],
    ]


def run_pipeline(
    args: argparse.Namespace, runner: Runner = subprocess_runner
) -> tuple[dict[str, object], dict[str, object]]:
    for command in pipeline_commands(args):
        runner(command)
    gamewords_report = json.loads(args.gamewords_summary.read_text(encoding="utf-8"))
    audit_report = json.loads(args.audit_json.read_text(encoding="utf-8"))
    if gamewords_report.get("saldo_affects_output") is not False:
        raise RuntimeError("Slutrapporten intygar inte att SALDO saknar påverkan på output.")
    if audit_report.get("affects_game_wordlist") is not False:
        raise RuntimeError("SALDO-rapporten är inte markerad som en ren audit.")
    return gamewords_report, audit_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build the canonical SAOL14-only game wordlist and then audit it against "
            "SALDO without allowing SALDO to change the output."
        )
    )
    parser.add_argument("--saol", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--saldo", type=Path, default=DEFAULT_SALDO)
    parser.add_argument("--shared-words", type=Path, default=DEFAULT_SHARED_WORDS)
    parser.add_argument("--shared-jsonl", type=Path, default=DEFAULT_SHARED_JSONL)
    parser.add_argument("--shared-summary", type=Path, default=DEFAULT_SHARED_SUMMARY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--gamewords-jsonl", type=Path, default=DEFAULT_GAMEWORDS_JSONL)
    parser.add_argument("--rejected", type=Path, default=DEFAULT_REJECTED)
    parser.add_argument("--gamewords-summary", type=Path, default=DEFAULT_GAMEWORDS_SUMMARY)
    parser.add_argument("--audit-text", type=Path, default=DEFAULT_AUDIT_TEXT)
    parser.add_argument("--audit-json", type=Path, default=DEFAULT_AUDIT_JSON)
    parser.add_argument("--only-saol", type=Path, default=DEFAULT_ONLY_SAOL)
    parser.add_argument("--only-saldo", type=Path, default=DEFAULT_ONLY_SALDO)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    gamewords, audit = run_pipeline(args)
    print("Kanoniskt SAOL14-bygge och fristående SALDO-audit klara.")
    print(f"Spelord: {gamewords['game_words']}")
    print(f"Bortfiltrerade SAOL-rader: {gamewords['rejected_rows']}")
    print(f"SALDO-granskningskandidater: {audit['saldo_only_with_exact_saol_lemma_and_upos_candidates']}")
    print(f"Spelordlista: {args.output}")
    print(f"Byggrapport: {args.gamewords_summary}")
    print(f"SALDO-audit: {args.audit_text}")


if __name__ == "__main__":
    main()
