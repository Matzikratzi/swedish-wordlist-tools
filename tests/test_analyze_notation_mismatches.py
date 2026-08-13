import unittest

from swedish_wordlist_tools.analyze_notation_mismatches import analyse_rows, render_text


class AnalyzeNotationMismatchesTests(unittest.TestCase):
    def test_lists_all_saldo_candidates_for_selected_notation(self) -> None:
        rows = [
            {
                "status": "form_set_mismatch",
                "notation": "+n +er",
                "lemma": "idé",
                "homonym_number": "1",
                "record_id": "42",
                "upos": "NOUN",
                "match_method": "lemma_same_upos",
                "generated_forms": ["idé", "idén", "idéer"],
                "saldo_forms": ["idé", "idén"],
                "extra_from_saol": ["idéer"],
                "missing_from_saol": [],
                "saldo_ids": ["idé..nn.1"],
                "saldo_lemmas": ["idé"],
            },
            {
                "status": "form_set_mismatch",
                "notation": "+en +ar",
                "lemma": "hund",
            },
        ]
        saldo = {
            "idé": [
                {
                    "id": "idé..nn.1",
                    "upos": "NOUN",
                    "lemmas": {"idé"},
                    "forms": {"idé", "idén"},
                },
                {
                    "id": "idé..nn.2",
                    "upos": "NOUN",
                    "lemmas": {"idé"},
                    "forms": {"idé", "idéer"},
                },
            ]
        }

        summary = analyse_rows(rows, saldo, "+n +er")

        self.assertEqual(1, summary["records"])
        self.assertEqual(2, len(summary["items"][0]["saldo_candidates"]))
        self.assertEqual("idé..nn.1", summary["items"][0]["selected_saldo_ids"][0])
        text = render_text(summary)
        self.assertIn("idé..nn.1 | NOUN [vald]", text)
        self.assertIn("idé..nn.2 | NOUN", text)


if __name__ == "__main__":
    unittest.main()
