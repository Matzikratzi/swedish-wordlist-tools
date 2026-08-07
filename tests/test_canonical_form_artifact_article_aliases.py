from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from swedish_wordlist_tools.canonical_form_artifacts import (
    forms_from_artifacts,
    read_artifact,
    read_artifact_variant_lemmas,
    variant_lemmas_from_artifact,
)


class CanonicalFormArtifactArticleAliasesTests(unittest.TestCase):
    def test_one_article_row_indexes_all_source_homonym_numbers(self) -> None:
        row = {
            "record_id": "5598",
            "article_id": "5598",
            "homonym_number": "1",
            "source_homonym_numbers": ["1", "0"],
            "lemma": "bankväsen",
            "variant_lemmas": ["bankväsen", "bankväsende"],
            "forms": [
                {"written_form": "bankväsen"},
                {"written_form": "bankväsende"},
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "noun.jsonl"
            path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
            forms = read_artifact(path)
            lemmas = read_artifact_variant_lemmas(path)

        artifacts = {"NOUN": forms}
        for homonr in ("1", "0"):
            raw = {
                "subnr": 5598,
                "homonr": homonr,
                "normaliserat_ord": "bankväsen",
                "upos": "NOUN",
            }
            self.assertEqual({"bankväsen", "bankväsende"}, forms_from_artifacts(raw, artifacts))
            self.assertEqual(("bankväsen", "bankväsende"), variant_lemmas_from_artifact(raw, lemmas))


if __name__ == "__main__":
    unittest.main()
