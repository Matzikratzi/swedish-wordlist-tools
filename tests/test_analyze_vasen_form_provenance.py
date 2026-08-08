import unittest

from swedish_wordlist_tools.analyze_vasen_form_provenance import analyze_rows


class AnalyzeVasenFormProvenanceTests(unittest.TestCase):
    def test_maps_generated_forms_to_canonical_heading_sources(self):
        validation = [{
            "upos": "NOUN",
            "notation": "+det; pl. +, best. pl. +dena _ +t +n",
            "mismatch_classification": "unclassified",
            "lemma": "bankväsen",
            "record_id": "5598",
            "homonym_number": "1",
            "coverage_status": "partial",
            "paradigm_status": "form_set_mismatch",
            "paradigm_reason": "primary_paradigm_difference",
            "match_method": "article_variant_lemmas_same_upos_partial",
            "generated_forms": ["bankväsen", "bankväsendet", "bankväsende"],
            "saldo_forms": ["bankväsen", "bankväsendet"],
            "extra_from_saol": ["bankväsende"],
            "missing_from_saol": [],
            "variant_validation": [],
        }]
        noun_rows = [{
            "record_id": "5598",
            "forms": [
                {
                    "written_form": "bankväsen",
                    "generated_from": [{"heading": "bankväsen", "heading_type": "primary", "article_id": "5598"}],
                },
                {
                    "written_form": "bankväsendet",
                    "generated_from": [
                        {"heading": "bankväsen", "heading_type": "primary", "article_id": "5598"},
                        {"heading": "bankväsende", "heading_type": "alternative", "article_id": "5598"},
                    ],
                },
                {
                    "written_form": "bankväsende",
                    "generated_from": [{"heading": "bankväsende", "heading_type": "alternative", "article_id": "5598"}],
                },
            ],
        }]
        summary = analyze_rows(validation, noun_rows)
        self.assertEqual(1, summary["rows"])
        row = summary["details"][0]
        self.assertEqual("bankväsen", row["form_provenance"]["bankväsen"][0]["heading"])
        self.assertEqual(2, len(row["form_provenance"]["bankväsendet"]))
        self.assertEqual("bankväsende", row["form_provenance"]["bankväsende"][0]["heading"])

    def test_ignores_other_notations(self):
        validation = [{
            "upos": "NOUN",
            "notation": "+en +er",
            "mismatch_classification": "unclassified",
            "record_id": "1",
        }]
        self.assertEqual(0, analyze_rows(validation, [])["rows"])


if __name__ == "__main__":
    unittest.main()
