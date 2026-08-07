from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from swedish_wordlist_tools.canonical_direct_forms import canonical_record_forms
from swedish_wordlist_tools.canonical_form_artifacts import (
    forms_from_artifacts,
    load_word_class_artifacts,
)
from swedish_wordlist_tools.revalidate_direct_forms import canonical_validation_row


class RevalidateDirectFormsTests(unittest.TestCase):
    def analysis(self, *forms: str) -> dict[str, object]:
        return {
            "id": "saldo.1",
            "lemmas": ["test"],
            "forms": list(forms),
            "upos": "",
        }

    def test_uses_canonical_adjective_generator_for_record_local_fallback(self) -> None:
        record = {
            "normaliserat_ord": "röd",
            "upos": "ADJ",
            "text": "rött röda",
            "stycke": "röd",
            "homonr": "1",
        }
        self.assertEqual({"röd", "rött", "röda"}, canonical_record_forms(record))

    def test_uses_canonical_verb_generator_for_record_local_fallback(self) -> None:
        record = {
            "normaliserat_ord": "abonnera",
            "upos": "VERB",
            "text": "+de +t",
            "stycke": "abonn·era",
            "homonr": "1",
        }
        self.assertEqual(
            {"abonnera", "abonnerade", "abonnerat"},
            canonical_record_forms(record),
        )

    def test_validation_row_accepts_precomputed_artifact_forms(self) -> None:
        record = {
            "normaliserat_ord": "apanage",
            "upos": "NOUN",
            "text": "+t [-et]; pl. +",
            "stycke": "apan·age",
            "homonr": "1",
            "subnr": "123",
        }
        generated = {
            "apanage",
            "apanages",
            "apanaget",
            "apanagets",
            "apanagen",
            "apanagens",
        }
        row = canonical_validation_row(
            record,
            "lemma_same_upos",
            [self.analysis(*sorted(generated))],
            generated_forms=generated,
            generator="canonical_artifact",
        )
        self.assertEqual("exact_form_set", row["status"])
        self.assertEqual("canonical_artifact", row["generator"])
        self.assertEqual([], row["missing_from_saol"])
        self.assertEqual([], row["extra_from_saol"])

    def test_artifact_lookup_uses_record_homonym_and_lemma(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            noun_path = root / "nouns.jsonl"
            adjective_path = root / "adjectives.jsonl"
            noun_rows = [
                {
                    "record_id": "123",
                    "homonym_number": "1",
                    "lemma": "apanage",
                    "forms": [
                        {"written_form": "apanage"},
                        {"written_form": "apanaget"},
                        {"written_form": "apanagen"},
                    ],
                },
                {
                    "record_id": "123",
                    "homonym_number": "2",
                    "lemma": "apanage",
                    "forms": [{"written_form": "annan-form"}],
                },
            ]
            noun_path.write_text(
                "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in noun_rows),
                encoding="utf-8",
            )
            adjective_path.write_text("", encoding="utf-8")
            artifacts = load_word_class_artifacts(
                noun_path=noun_path,
                adjective_path=adjective_path,
            )
            record = {
                "subnr": "123",
                "homonr": "1",
                "normaliserat_ord": "apanage",
                "upos": "NOUN",
            }
            self.assertEqual(
                {"apanage", "apanaget", "apanagen"},
                forms_from_artifacts(record, artifacts),
            )


if __name__ == "__main__":
    unittest.main()
