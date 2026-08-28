import unittest

from swedish_wordlist_tools.ocr_jsonl_page_hints import align_ocr_words, reference_tokens, visible_row_prefix
from swedish_wordlist_tools.ocr_unique_unknown_glyph_review import _jsonl_group_suggestions


class JsonlPageHintsTest(unittest.TestCase):
    def test_visible_prefix_limits_only_text_field(self):
        row = {"stycke": "ab·ba s.", "text": "x" * 80}
        value = visible_row_prefix(row, text_limit=50)
        self.assertTrue(value.startswith("ab·ba s. "))
        self.assertEqual(len(value.split(" ", 2)[-1]), 50)

    def test_monotonic_alignment_survives_bad_ocr_token(self):
        refs = reference_tokens([
            {"stycke": "abba s.", "text": "+n +r vanlig", "subnr": 1},
            {"stycke": "abbé s.", "text": "+n", "subnr": 2},
        ])
        aligned = align_ocr_words(["abba", "zzz", "abbé"], refs)
        self.assertEqual(aligned[0]["text"], "abba")
        self.assertIsNone(aligned[1])
        self.assertEqual(aligned[2]["text"], "abbé")

    def test_unknown_between_exact_anchors_gets_jsonl_character(self):
        left = {(0, 0)}
        unknown = {(2, 0), (2, 1)}
        right = {(4, 0)}
        row = {
            "jsonl_hint": {"text": "abc"},
            "exact": [
                {"label": "a", "style": "bold", "pixels": [list(p) for p in left]},
                {"label": "c", "style": "bold", "pixels": [list(p) for p in right]},
            ],
        }
        self.assertEqual(_jsonl_group_suggestions(row, [unknown]), ["b{b}"])


if __name__ == "__main__":
    unittest.main()
