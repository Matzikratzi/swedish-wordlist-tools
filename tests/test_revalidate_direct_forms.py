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
from swedish_wordlist_tools.revalidate_direct_forms import (
    _semantic_status,
    canonical_validation_row,
    select_article_variant_match_from_artifacts,
    select_direct_match_from_artifacts,
)


class RevalidateDirectFormsTests(unittest.TestCase):
    def analysis(self, *forms: str, upos: str = "") -> dict[str, object]:
        return {
            "id": "saldo.1",
            "lemmas": ["test"],
            "forms": list(forms),
            "upos": upos,
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
        self.assertEqual("exact_form_set", row["semantic_status"])
        self.assertEqual("canonical_artifact", row["generator"])
        self.assertEqual([], row["missing_from_saol"])
        self.assertEqual([], row["extra_from_saol"])

    def test_homonym_selection_uses_supplied_artifact_forms(self) -> None:
        record = {
            "normaliserat_ord": "test",
            "upos": "NOUN",
            "ordkl": "s.",
        }
        exact = self.analysis("test", "testen", upos="NOUN")
        other = self.analysis("test", "tester", upos="NOUN")
        exact["id"] = "exact"
        other["id"] = "other"
        saldo = {"test": [other, exact]}
        selected = select_direct_match_from_artifacts(
            record,
            saldo,
            {},
            {"test", "testen"},
        )
        self.assertIsNotNone(selected)
        method, analyses = selected
        self.assertEqual("lemma_same_upos", method)
        self.assertEqual(["exact"], [analysis["id"] for analysis in analyses])

    def test_single_rebased_variant_matches_written_lemma_not_normalized_carrier(self) -> None:
        record = {
            "normaliserat_ord": "akne",
            "ord": "acne",
            "upos": "NOUN",
        }
        acne = {
            "id": "acne.nn.1",
            "lemmas": ["acne"],
            "forms": ["acne", "acnes", "acnen", "acnens"],
            "upos": "NOUN",
        }
        akne = {
            "id": "akne.nn.1",
            "lemmas": ["akne"],
            "forms": ["akne", "aknes", "aknen", "aknens"],
            "upos": "NOUN",
        }
        saldo = {"acne": [acne], "akne": [akne]}
        generated = {"acne", "acnes", "acnen", "acnens"}
        selected = select_article_variant_match_from_artifacts(
            record,
            saldo,
            {},
            generated,
            {"acne": generated},
        )
        self.assertIsNotNone(selected)
        method, analyses = selected
        self.assertEqual("single_article_variant_lemma_same_upos", method)
        self.assertEqual(["acne.nn.1"], [analysis["id"] for analysis in analyses])

    def test_single_primary_paradigm_keeps_normal_direct_lookup(self) -> None:
        record = {
            "normaliserat_ord": "akne",
            "ord": "akne",
            "upos": "NOUN",
        }
        akne = {
            "id": "akne.nn.1",
            "lemmas": ["akne"],
            "forms": ["akne", "aknen"],
            "upos": "NOUN",
        }
        saldo = {"akne": [akne]}
        selected = select_article_variant_match_from_artifacts(
            record,
            saldo,
            {},
            {"akne", "aknen"},
            {"akne": {"akne", "aknen"}},
        )
        self.assertIsNotNone(selected)
        method, analyses = selected
        self.assertEqual("lemma_same_upos", method)
        self.assertEqual(["akne.nn.1"], [analysis["id"] for analysis in analyses])

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

    def test_missing_alternative_heading_is_variant_coverage_difference(self) -> None:
        semantic, reason = _semantic_status(
            "form_set_mismatch",
            [
                {
                    "lemma": "brevbäring",
                    "heading_type": "primary",
                    "status": "exact_form_set",
                },
                {
                    "lemma": "brevbärning",
                    "heading_type": "alternative",
                    "status": "variant_missing_in_saldo",
                },
            ],
        )
        self.assertEqual("variant_coverage_difference", semantic)
        self.assertEqual("alternative_heading_missing_in_saldo", reason)

    def test_non_variant_mismatch_remains_true_form_mismatch(self) -> None:
        semantic, reason = _semantic_status("form_set_mismatch", [])
        self.assertEqual("true_form_mismatch", semantic)
        self.assertEqual("non_variant_form_difference", reason)


if __name__ == "__main__":
    unittest.main()
