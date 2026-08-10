import json
import tempfile
import unittest
from pathlib import Path

from swedish_wordlist_tools.canonical_form_artifacts import (
    artifact_row_keys,
    forms_from_artifacts,
    load_word_class_artifacts,
)
from swedish_wordlist_tools.generate_noun_forms import generate_noun_artifact
from swedish_wordlist_tools.saol_noun_variants import (
    is_simple_relative_noun_notation,
    prepare_noun_variant_records,
)


class SaolNounVariantTests(unittest.TestCase):
    def test_simple_relative_notation_is_narrow(self):
        self.assertTrue(is_simple_relative_noun_notation("+n"))
        self.assertTrue(is_simple_relative_noun_notation("+en +er"))
        self.assertTrue(is_simple_relative_noun_notation("+et; pl. +"))
        self.assertFalse(is_simple_relative_noun_notation("+det; pl. +, best. pl. +dena _ +t +n"))
        self.assertFalse(is_simple_relative_noun_notation("+et el. +en"))
        self.assertFalse(is_simple_relative_noun_notation("+n [-en]"))
        self.assertFalse(is_simple_relative_noun_notation("ankaret; pl. ankare el. ankaren, best. pl. ankarna"))

    def _acne_records(self):
        return [
            {"normaliserat_ord": "akne", "homonr": "0", "subnr": 438305, "ordkl": "s. +n", "stycke": "akne", "text": "+n", "upos": "NOUN", "ord": "acne"},
            {"normaliserat_ord": "akne", "homonr": "1", "subnr": 436676, "ordkl": "(hv)", "stycke": "acne", "text": "(null)", "upos": "X", "ord": "acne"},
        ]

    def test_matching_hv_rebases_simple_acne_paradigm(self):
        prepared = prepare_noun_variant_records(self._acne_records())
        noun = prepared[0]
        self.assertEqual("acne", noun["normaliserat_ord"])
        self.assertEqual("akne", noun["_saol_source_normaliserat_ord"])
        self.assertEqual("rebase_simple_relative", noun["_saol_variant_mode"])
        rows, _comparisons, _summary = generate_noun_artifact(prepared)
        forms = {item["written_form"] for item in rows[0]["forms"]}
        self.assertEqual({"acne", "acnes", "acnen", "acnens"}, forms)

    def test_rebased_artifact_keeps_written_key_not_normalized_alias(self):
        prepared = prepare_noun_variant_records(self._acne_records())
        rows, _comparisons, _summary = generate_noun_artifact(prepared)
        keys = set(artifact_row_keys(rows[0]))
        self.assertIn(("438305", "0", "acne"), keys)
        self.assertNotIn(("438305", "0", "akne"), keys)

    def test_raw_variant_row_finds_its_written_artifact(self):
        prepared = prepare_noun_variant_records(self._acne_records())
        rows, _comparisons, _summary = generate_noun_artifact(prepared)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            noun_path = root / "nouns.jsonl"
            adjective_path = root / "adjectives.jsonl"
            noun_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
            adjective_path.write_text("", encoding="utf-8")
            artifacts = load_word_class_artifacts(noun_path=noun_path, adjective_path=adjective_path)
            forms = forms_from_artifacts(self._acne_records()[0], artifacts)
            self.assertEqual({"acne", "acnes", "acnen", "acnens"}, forms)

    def test_hv_is_required_before_rebasing_single_branch_ord_variant(self):
        records = [{"normaliserat_ord": "akne", "homonr": "0", "subnr": 1, "ordkl": "s. +n", "stycke": "akne", "text": "+n", "upos": "NOUN", "ord": "acne"}]
        prepared = prepare_noun_variant_records(records)
        self.assertEqual("akne", prepared[0]["normaliserat_ord"])
        self.assertNotIn("_saol_variant_mode", prepared[0])

    def test_ankar_is_not_rebased(self):
        records = [
            {"normaliserat_ord": "ankare", "homonr": "0", "subnr": 442860, "ordkl": "s. ankaret; pl. anka...", "stycke": "1ankare", "text": "ankaret; pl. ankare el. ankaren, best. pl. ankarna", "upos": "NOUN", "ord": "ankar"},
            {"normaliserat_ord": "ankare", "homonr": "1", "subnr": 442848, "ordkl": "(hv)", "stycke": "ankar", "text": "(null)", "upos": "X", "ord": "ankar"},
        ]
        prepared = prepare_noun_variant_records(records)
        noun = prepared[0]
        self.assertEqual("ankare", noun["normaliserat_ord"])
        self.assertEqual("ankar", noun["_saol_alternative_lemma"])
        self.assertEqual("additional_lemma", noun["_saol_variant_mode"])

    def test_two_branch_vasen_uses_explicit_variant_as_second_base(self):
        records = [
            {
                "normaliserat_ord": "bankväsen",
                "homonr": "0",
                "subnr": 100,
                "ordkl": "s.",
                "stycke": "bank|väsen",
                "text": "+det; pl. +, best. pl. +dena _ +t +n",
                "upos": "NOUN",
                "ord": "bankväsende",
            },
            {
                "normaliserat_ord": "bankväsen",
                "homonr": "1",
                "subnr": 101,
                "ordkl": "(hv)",
                "stycke": "bankväsende",
                "text": "(null)",
                "upos": "X",
                "ord": "bankväsende",
            },
        ]
        prepared = prepare_noun_variant_records(records)
        self.assertEqual("additional_lemma", prepared[0]["_saol_variant_mode"])
        rows, _comparisons, _summary = generate_noun_artifact(prepared)
        forms = {item["written_form"] for item in rows[0]["forms"]}
        self.assertEqual(
            {
                "bankväsen", "bankväsens", "bankväsende", "bankväsendes",
                "bankväsendet", "bankväsendets", "bankväsenden", "bankväsendens",
                "bankväsendena", "bankväsendenas",
            },
            forms,
        )

    def test_duplicate_noun_rows_bind_hajp_and_hype_to_separate_branches(self):
        records = [
            {
                "normaliserat_ord": "hajp", "homonr": "1", "subnr": 386768,
                "ordkl": "s. +en; pl. +er el. ...", "stycke": "hajp",
                "text": "+en; pl. +er el. +ar _ +n [haj>pen]",
                "upos": "NOUN", "ord": "hajp",
            },
            {
                "normaliserat_ord": "hajp", "homonr": "0", "subnr": 386768,
                "ordkl": "s. +en; pl. +er el. ...", "stycke": "hajp",
                "text": "+en; pl. +er el. +ar _ +n [haj>pen]",
                "upos": "NOUN", "ord": "hype",
            },
        ]
        prepared = prepare_noun_variant_records(records)
        for row in prepared:
            self.assertEqual("hype", row["_saol_alternative_lemma"])
            self.assertEqual("duplicate_noun_article_rows", row["_saol_variant_evidence"])

        rows, _comparisons, _summary = generate_noun_artifact(prepared)
        for artifact in rows:
            forms = {item["written_form"] for item in artifact["forms"]}
            self.assertEqual(
                {
                    "hajp", "hajps", "hajpen", "hajpens",
                    "hajper", "hajpers", "hajperna", "hajpernas",
                    "hajpar", "hajpars", "hajparna", "hajparnas",
                    "hype", "hypes", "hypen", "hypens",
                },
                forms,
            )
            self.assertNotIn("hajpn", forms)

    def test_allan_cross_reference_alone_does_not_create_noun_variant(self):
        records = [{"normaliserat_ord": "all", "homonr": "0", "subnr": 1, "ordkl": "(hv)", "stycke": "allan", "text": "(null)", "upos": "X", "ord": "allan"}]
        prepared = prepare_noun_variant_records(records)
        self.assertEqual(records, prepared)

    def test_disko_and_disco_keep_separate_written_paradigms(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            noun_path = root / "nouns.jsonl"
            adjective_path = root / "adjectives.jsonl"
            noun_rows = [
                {"record_id": "428401", "homonym_number": "1", "lemma": "disko", "forms": [{"written_form": "disko"}, {"written_form": "diskot"}]},
                {"record_id": "428401", "homonym_number": "1", "lemma": "disco", "source_normaliserat_ord": "disko", "forms": [{"written_form": "disco"}, {"written_form": "discot"}]},
            ]
            noun_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in noun_rows), encoding="utf-8")
            adjective_path.write_text("", encoding="utf-8")
            artifacts = load_word_class_artifacts(noun_path=noun_path, adjective_path=adjective_path)
            disko = {"subnr": "428401", "homonr": "1", "normaliserat_ord": "disko", "ord": "disko", "upos": "NOUN"}
            disco = dict(disko, ord="disco")
            self.assertEqual({"disko", "diskot"}, forms_from_artifacts(disko, artifacts))
            self.assertEqual({"disco", "discot"}, forms_from_artifacts(disco, artifacts))


if __name__ == "__main__":
    unittest.main()
