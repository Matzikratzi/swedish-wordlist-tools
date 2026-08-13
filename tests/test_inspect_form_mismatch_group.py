import unittest

from swedish_wordlist_tools.inspect_form_mismatch_group import render_rows, select_rows


class InspectFormMismatchGroupTests(unittest.TestCase):
    def test_selects_only_current_exact_group(self):
        rows = [
            {
                "status": "form_set_mismatch",
                "lemma": "bankväsen",
                "homonym_number": "1",
                "upos": "NOUN",
                "notation": "+det; pl. +, best. pl. +dena _ +t +n",
            },
            {
                "status": "exact_form_set",
                "lemma": "bandage",
                "homonym_number": "1",
                "upos": "NOUN",
                "notation": "+t [-et]; pl. +",
            },
            {
                "status": "form_set_mismatch",
                "lemma": "delvis",
                "homonym_number": "1",
                "upos": "X",
                "notation": "+t +a",
            },
        ]
        selected = select_rows(
            rows,
            upos="NOUN",
            notation="+det; pl. +, best. pl. +dena _ +t +n",
        )
        self.assertEqual(["bankväsen"], [row["lemma"] for row in selected])

    def test_renders_complete_form_sets_and_differences(self):
        text = render_rows(
            [
                {
                    "lemma": "bankväsen",
                    "homonym_number": "1",
                    "upos": "NOUN",
                    "notation": "+det; pl. +, best. pl. +dena _ +t +n",
                    "record_id": "1",
                    "generator": "canonical_artifact",
                    "match_method": "lemma_same_upos",
                    "generated_forms": ["bankväsen", "bankväsendet"],
                    "saldo_forms": ["bankväsen", "bankväsenet"],
                    "extra_from_saol": ["bankväsendet"],
                    "missing_from_saol": ["bankväsenet"],
                }
            ]
        )
        self.assertIn("SAOL-generator: bankväsen, bankväsendet", text)
        self.assertIn("SALDO: bankväsen, bankväsenet", text)
        self.assertIn("Extra från SAOL: bankväsendet", text)
        self.assertIn("Saknas från SAOL: bankväsenet", text)


if __name__ == "__main__":
    unittest.main()
