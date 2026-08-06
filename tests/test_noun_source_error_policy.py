from __future__ import annotations

import unittest

from swedish_wordlist_tools.inflect import generate_entry
from swedish_wordlist_tools.noun_paradigm import complete_noun_entry
from swedish_wordlist_tools.saol_notation import tokenize_notation


class NounSourceErrorPolicyTests(unittest.TestCase):
    def test_k_markup_preserves_only_lemma(self) -> None:
        for lemma, pattern in (
            ("fansin", "+et; pl. + _ +t [-et]; pl. + H +<k>s</k>"),
            ("nåd", "+en; de: åld. formerna: <k>nåde</k> och: <k>nåder<"),
            ("testord", "+n <K>godtyckligt</K>"),
        ):
            record = {
                "normaliserat_ord": lemma,
                "upos": "NOUN",
                "ordkl": "subst.",
                "text": pattern,
            }
            entry = complete_noun_entry(record, generate_entry(record))
            self.assertIsNotNone(entry)
            assert entry is not None
            self.assertEqual((lemma,), entry.forms)
            self.assertEqual("source-error lemma only", entry.pattern_group)

    def test_drops_truncated_final_token_only_at_source_limit(self) -> None:
        truncated = "dagen-efter-pillret; pl. +, best. pl. dagen-efter-"
        self.assertEqual(50, len(truncated))
        self.assertEqual(
            (
                "dagen-efter-pillret",
                ";",
                "pl.",
                "+",
                ",",
                "best.",
                "pl.",
            ),
            tokenize_notation(truncated),
        )

        shorter = "+n; kommentar-"
        self.assertLess(len(shorter), 50)
        self.assertIn("kommentar-", tokenize_notation(shorter) or ())

    def test_truncated_dagen_efter_piller_uses_remaining_notation(self) -> None:
        record = {
            "normaliserat_ord": "dagen-efter-piller",
            "upos": "NOUN",
            "ordkl": "subst.",
            "stycke": "dag·en-efter-piller",
            "text": "dagen-efter-pillret; pl. +, best. pl. dagen-efter-",
        }
        entry = complete_noun_entry(record, generate_entry(record))
        self.assertIsNotNone(entry)
        assert entry is not None
        forms = set(entry.forms)
        self.assertIn("dagen-efter-piller", forms)
        self.assertIn("dagen-efter-pillret", forms)
        self.assertNotIn("dagen-efter-", forms)
        self.assertNotIn("dagen-efter-pillefter", forms)


if __name__ == "__main__":
    unittest.main()
