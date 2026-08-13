import unittest

from swedish_wordlist_tools.analyze_unclassified_noun_mismatches import analyze_rows


class AnalyzeUnclassifiedNounMismatchesTests(unittest.TestCase):
    def test_selects_only_unclassified_nouns_and_groups_exact_structure(self):
        rows = [
            {
                "upos": "NOUN",
                "mismatch_classification": "unclassified",
                "lemma": "alpha",
                "homonym_number": "1",
                "record_id": "1",
                "notation": "+et",
                "extra_from_saol": ["alphaet", "alphaets"],
                "missing_from_saol": ["alphaen", "alphaens"],
                "match_method": "lemma_same_upos",
                "coverage_status": "not_applicable",
                "paradigm_reason": "non_variant_form_difference",
            },
            {
                "upos": "NOUN",
                "mismatch_classification": "unclassified",
                "lemma": "beta",
                "homonym_number": "1",
                "record_id": "2",
                "notation": "+et",
                "extra_from_saol": ["betaet", "betaets"],
                "missing_from_saol": ["betaen", "betaens"],
                "match_method": "lemma_same_upos",
                "coverage_status": "not_applicable",
                "paradigm_reason": "non_variant_form_difference",
            },
            {
                "upos": "ADJ",
                "mismatch_classification": "unclassified",
                "lemma": "gamma",
                "notation": "+t +a",
            },
            {
                "upos": "NOUN",
                "mismatch_classification": "saldo_missing_plural",
                "lemma": "delta",
                "notation": "+en +er",
            },
        ]

        summary = analyze_rows(rows)
        self.assertEqual(2, summary["records"])
        self.assertEqual(1, summary["structure_groups"])
        group = summary["groups"][0]
        self.assertEqual(2, group["count"])
        self.assertEqual("+et", group["notation"])
        self.assertEqual(["+et", "+ets"], group["extra_pattern"])
        self.assertEqual(["+en", "+ens"], group["missing_pattern"])
        self.assertEqual(["alpha", "beta"], [item["lemma"] for item in group["examples"]])

    def test_distinguishes_match_and_coverage_axes(self):
        base = {
            "upos": "NOUN",
            "mismatch_classification": "unclassified",
            "lemma": "foo",
            "notation": "+en",
            "extra_from_saol": ["fooen"],
            "missing_from_saol": [],
            "paradigm_reason": "primary_paradigm_difference",
        }
        rows = [
            {**base, "match_method": "lemma_same_upos", "coverage_status": "not_applicable"},
            {**base, "match_method": "article_variant_lemmas_same_upos_partial", "coverage_status": "partial"},
        ]
        summary = analyze_rows(rows)
        self.assertEqual(2, summary["structure_groups"])


if __name__ == "__main__":
    unittest.main()
