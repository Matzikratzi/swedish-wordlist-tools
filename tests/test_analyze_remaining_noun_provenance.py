from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_remaining_noun_provenance import analyze


class RemainingNounProvenanceTests(unittest.TestCase):
    def test_separates_direct_and_derived_extras_after_standard_filter(self) -> None:
        validation = [
            {
                "record_id": "1", "homonym_number": "1", "lemma": "hund", "upos": "NOUN",
                "status": "form_set_mismatch", "notation": "+en el. vard. -dan; pl. +ar",
                "extra_from_saol": ["hundar", "hundarna"], "missing_from_saol": [],
            },
            {
                "record_id": "2", "homonym_number": "1", "lemma": "katt", "upos": "NOUN",
                "status": "form_set_mismatch", "notation": "+n; pl. + H +s",
                "extra_from_saol": ["katter"], "missing_from_saol": [],
            },
            {
                "record_id": "3", "homonym_number": "1", "lemma": "agens", "upos": "NOUN",
                "status": "form_set_mismatch", "notation": "+en +er",
                "extra_from_saol": ["agenser"], "missing_from_saol": [],
            },
        ]
        artifacts = [
            {
                "record_id": "1", "homonym_number": "1", "lemma": "hund",
                "forms": [
                    {"written_form": "hundar", "kind": "interpreted_slot"},
                    {"written_form": "hundarna", "kind": "derived_definite_plural"},
                ],
            },
            {
                "record_id": "2", "homonym_number": "1", "lemma": "katt",
                "forms": [{"written_form": "katter", "kind": "interpreted_slot"}],
            },
            {
                "record_id": "3", "homonym_number": "1", "lemma": "agens",
                "forms": [{"written_form": "agenser", "kind": "interpreted_slot"}],
            },
        ]
        summary = analyze(validation, artifacts)
        self.assertEqual(2, summary["records"])
        self.assertEqual(1, summary["bucket_counts"]["mixed_direct_and_derived"])
        self.assertEqual(1, summary["bucket_counts"]["direct_saol_slots_only"])
        self.assertEqual(1, summary["extra_form_kind_counts"]["derived_definite_plural"])
        self.assertEqual(2, summary["extra_form_kind_counts"]["interpreted_slot"])

    def test_ignores_non_noun_non_mismatch_and_mechanical_rows(self) -> None:
        validation = [
            {"record_id": "1", "homonym_number": "1", "lemma": "fin", "upos": "ADJ", "status": "form_set_mismatch"},
            {"record_id": "2", "homonym_number": "1", "lemma": "hund", "upos": "NOUN", "status": "exact_form_set"},
            {"record_id": "3", "homonym_number": "1", "lemma": "ämne", "upos": "NOUN", "status": "form_set_mismatch", "notation": "+t +n"},
        ]
        summary = analyze(validation, [])
        self.assertEqual(0, summary["records"])
        self.assertEqual({}, summary["bucket_counts"])


if __name__ == "__main__":
    unittest.main()
