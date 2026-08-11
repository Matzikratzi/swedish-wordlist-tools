from __future__ import annotations

import unittest

from swedish_wordlist_tools.saol_source_policy import is_truncated_inflection_source


class SaolSourcePolicyTests(unittest.TestCase):
    def test_exact_fifty_character_source_is_truncated(self) -> None:
        self.assertTrue(is_truncated_inflection_source({"text": "x" * 50}))

    def test_sachsare_style_49_character_dangling_label_is_truncated(self) -> None:
        text = "+n; pl. +, best. pl. sachsarna _ +n; pl. +, best."
        self.assertEqual(49, len(text))
        self.assertTrue(is_truncated_inflection_source({"text": text}))

    def test_ta_style_49_character_qualified_alternative_is_truncated(self) -> None:
        text = "tog, tagit, tagen taget tagna, pres. tar el. åld."
        self.assertEqual(49, len(text))
        self.assertTrue(is_truncated_inflection_source({"text": text}))

    def test_ordinary_49_character_source_is_not_assumed_truncated(self) -> None:
        self.assertFalse(is_truncated_inflection_source({"text": "x" * 49}))

    def test_bare_editorial_qualifier_at_49_is_not_enough(self) -> None:
        text = "x" * 44 + " åld."
        self.assertEqual(49, len(text))
        self.assertFalse(is_truncated_inflection_source({"text": text}))

    def test_short_complete_label_is_not_assumed_truncated(self) -> None:
        self.assertFalse(is_truncated_inflection_source({"text": "best."}))


if __name__ == "__main__":
    unittest.main()
