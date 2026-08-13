from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from swedish_wordlist_tools.build_game_wordlist_pipeline import (
    assert_clean_audit,
    build_parser,
    pipeline_commands,
    run_pipeline,
    summary_lines,
)


class BuildGameWordlistPipelineTests(unittest.TestCase):
    def test_builds_three_commands_in_dependency_order(self) -> None:
        args = build_parser().parse_args([])
        commands = pipeline_commands(args)
        self.assertEqual(3, len(commands))
        self.assertIn("swedish_wordlist_tools.generate_adjective_forms", commands[0])
        self.assertIn("swedish_wordlist_tools.game_wordlist", commands[1])
        self.assertIn("swedish_wordlist_tools.audit_game_adjective_integration", commands[2])
        self.assertIn("--adjudication", commands[2])
        self.assertIn("--added", commands[2])

    def test_accepts_clean_audit(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "audit.json"
            path.write_text(
                json.dumps({"integration_is_clean": True, "added_game_words": 94}),
                encoding="utf-8",
            )
            report = assert_clean_audit(path)
            self.assertTrue(report["integration_is_clean"])

    def test_rejects_dirty_audit(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "audit.json"
            path.write_text(
                json.dumps({"integration_is_clean": False}),
                encoding="utf-8",
            )
            with self.assertRaises(RuntimeError):
                assert_clean_audit(path)

    def test_pipeline_runs_all_steps_and_checks_report(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            args = build_parser().parse_args([
                "--audit-json", str(root / "audit.json"),
            ])
            seen: list[list[str]] = []

            def runner(command: list[str]) -> None:
                seen.append(list(command))
                if "swedish_wordlist_tools.audit_game_adjective_integration" in command:
                    args.audit_json.write_text(
                        json.dumps({"integration_is_clean": True}),
                        encoding="utf-8",
                    )

            report = run_pipeline(args, runner)
            self.assertEqual(3, len(seen))
            self.assertTrue(report["integration_is_clean"])

    def test_summary_uses_integrated_game_word_count(self) -> None:
        args = build_parser().parse_args([])
        lines = summary_lines(
            {
                "integration_is_clean": True,
                "integrated_game_words": 577121,
                "added_game_words": 13962,
            },
            args,
        )
        self.assertIn("Ord i spelordlistan: 577121", lines)
        self.assertIn("Tillagda adjektivformer: 13962", lines)
        self.assertNotIn("Ord i spelordlistan: ?", lines)


if __name__ == "__main__":
    unittest.main()
