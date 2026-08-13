from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from swedish_wordlist_tools.build_final_wordlist_pipeline import (
    build_parser,
    pipeline_commands,
    run_pipeline,
)


class BuildFinalWordlistPipelineTests(unittest.TestCase):
    def test_runs_saol_build_then_finaliser_then_read_only_saldo_audit(self) -> None:
        commands = pipeline_commands(build_parser().parse_args([]))
        self.assertEqual(3, len(commands))
        self.assertIn("swedish_wordlist_tools.build_shared_wordlist", commands[0])
        self.assertIn("swedish_wordlist_tools.build_final_wordlist", commands[1])
        self.assertIn("swedish_wordlist_tools.audit_final_wordlist_saldo", commands[2])

    def test_requires_reports_to_state_that_saldo_does_not_affect_output(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            args = build_parser().parse_args([
                "--gamewords-summary", str(root / "build.json"),
                "--audit-json", str(root / "audit.json"),
            ])

            def runner(command: list[str]) -> None:
                if "swedish_wordlist_tools.build_final_wordlist" in command:
                    args.gamewords_summary.write_text(
                        json.dumps({"saldo_affects_output": False, "game_words": 2}),
                        encoding="utf-8",
                    )
                if "swedish_wordlist_tools.audit_final_wordlist_saldo" in command:
                    args.audit_json.write_text(
                        json.dumps({"affects_game_wordlist": False}), encoding="utf-8"
                    )

            build, audit_report = run_pipeline(args, runner)
            self.assertEqual(2, build["game_words"])
            self.assertFalse(audit_report["affects_game_wordlist"])


if __name__ == "__main__":
    unittest.main()
