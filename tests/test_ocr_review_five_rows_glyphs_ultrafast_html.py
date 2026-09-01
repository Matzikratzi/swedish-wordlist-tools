import unittest

from swedish_wordlist_tools import ocr_review_five_rows_glyphs_fast_html as fast
from swedish_wordlist_tools import ocr_review_five_rows_glyphs_ultrafast_html as ultrafast
from swedish_wordlist_tools.ocr_probe_row_glyphs_grouped import analyse_row_exact_grouped


class UltrafastFiveRowGlyphReviewTests(unittest.TestCase):
    def test_fast_editor_is_patched_to_grouped_matcher(self):
        self.assertIs(ultrafast.fast, fast)
        self.assertIs(fast.analyse_row_exact, analyse_row_exact_grouped)


if __name__ == "__main__":
    unittest.main()
