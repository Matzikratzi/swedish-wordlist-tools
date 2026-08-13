from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from swedish_wordlist_tools.export_verb_forms import build_verb_forms


class ExportVerbFormsTests(unittest.TestCase):
    def write_jsonl(self, records: list[dict[str, object]]) -> Path:
        handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".jsonl", delete=False)
        with handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        path = Path(handle.name)
        self.addCleanup(path.unlink, missing_ok=True)
        return path

    def test_default_export_is_saol_only(self) -> None:
        path = self.write_jsonl([
            {
                "normaliserat_ord": "skriva",
                "text": "skrev, skrivit, skriven skrivet skrivna, pres. skriver",
                "stycke": "skriva",
                "upos": "VERB",
                "ordkl": "v.",
            }
        ])

        words, report = build_verb_forms(path)

        self.assertEqual("SAOL14", report["source"])
        self.assertEqual("shared_saol", report["row_interpreter"])
        self.assertFalse(report["include_saldo"])
        self.assertFalse(report["include_validated_imperatives"])
        self.assertIn("skriva", words)
        self.assertIn("skrev", words)
        self.assertIn("skrivit", words)
        self.assertIn("skriven", words)
        self.assertIn("skrivet", words)
        self.assertIn("skrivna", words)
        self.assertIn("skriver", words)
        self.assertNotIn("saldo", report["unique_forms_by_provenance"])

    def test_shared_export_uses_saol_lodstreck(self) -> None:
        path = self.write_jsonl([
            {
                "normaliserat_ord": "handha",
                "text": "-hade, -haft, -havd -haft -havda, pres. -har",
                "stycke": "hand|ha",
                "upos": "VERB",
                "ordkl": "v.",
            }
        ])

        words, report = build_verb_forms(path)

        self.assertEqual("shared_saol", report["row_interpreter"])
        self.assertIn("handhade", words)
        self.assertIn("handhaft", words)
        self.assertIn("handhavd", words)
        self.assertIn("handhavda", words)
        self.assertIn("handhar", words)
        self.assertNotIn("hade", words)

    def test_includes_explicit_saol_imperative_without_saldo(self) -> None:
        path = self.write_jsonl([
            {
                "normaliserat_ord": "glädjas",
                "text": "gladdes, glatts, pres. gläds, imper. gläds",
                "stycke": "glädjas",
                "upos": "VERB",
                "ordkl": "v.",
            }
        ])

        words, report = build_verb_forms(path)

        self.assertIn("gläds", words)
        self.assertIn("explicit_saol_imperative", report["unique_forms_by_provenance"])

    def test_includes_reviewed_saol_hv_inflection(self) -> None:
        path = self.write_jsonl([
            {
                "normaliserat_ord": "spörja",
                "text": "sporde, sport, pres. spörjer",
                "stycke": "spörja",
                "ord": "spörja",
                "upos": "VERB",
                "ordkl": "v.",
            },
            {
                "normaliserat_ord": "spörja",
                "homonr": "0",
                "ordkl": "(hv)",
                "upos": "X",
                "text": "(null)",
                "stycke": "spörs",
                "ord": "spörs",
            },
        ])

        words, report = build_verb_forms(path)

        self.assertIn("spörs", words)
        self.assertEqual(1, report["unique_forms_by_provenance"]["reviewed_hv_inflection"])

    def test_rejects_multiword_and_nonalphabetic_forms_for_game_export(self) -> None:
        path = self.write_jsonl([
            {
                "normaliserat_ord": "loma av",
                "text": None,
                "stycke": "loma",
                "upos": "VERB",
                "ordkl": "v.",
            }
        ])

        words, report = build_verb_forms(path)

        self.assertEqual([], words)
        self.assertEqual(0, report["unique_playable_forms"])


if __name__ == "__main__":
    unittest.main()
