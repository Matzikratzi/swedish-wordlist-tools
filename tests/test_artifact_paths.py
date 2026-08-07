from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from swedish_wordlist_tools import artifact_paths


class ArtifactPathsTests(unittest.TestCase):
    def test_canonical_project_relative_paths(self) -> None:
        self.assertEqual(
            Path("data/processed/saol14-gamewords.txt"),
            artifact_paths.SAOL14_GAMEWORDS,
        )
        self.assertEqual(
            Path("reports/saol14-noun-forms.jsonl"),
            artifact_paths.SAOL14_NOUN_FORMS,
        )
        self.assertEqual(
            Path("reports/saol14-adjective-forms.jsonl"),
            artifact_paths.SAOL14_ADJECTIVE_FORMS,
        )
        self.assertEqual(
            Path("data/processed/saol14-verb-forms.txt"),
            artifact_paths.SAOL14_VERB_FORMS,
        )

    def test_absolute_gamewords_path_is_under_project_root(self) -> None:
        self.assertEqual(
            artifact_paths.PROJECT_ROOT / artifact_paths.SAOL14_GAMEWORDS,
            artifact_paths.absolute_gamewords_path(),
        )

    def test_require_gamewords_reports_the_official_path(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            with patch.object(artifact_paths, "PROJECT_ROOT", Path(tempdir)):
                with self.assertRaisesRegex(
                    FileNotFoundError,
                    r"data/processed/saol14-gamewords\.txt",
                ):
                    artifact_paths.require_gamewords()

    def test_cli_always_prints_the_official_project_path(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            artifact_paths.main()
        self.assertIn(
            "projekt: data/processed/saol14-gamewords.txt",
            output.getvalue(),
        )


if __name__ == "__main__":
    unittest.main()
