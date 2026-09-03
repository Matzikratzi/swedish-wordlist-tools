from types import SimpleNamespace
import unittest

from swedish_wordlist_tools.ocr_find_unreviewed_glyph_rows import (
    _selected_pages,
    classify_row_state,
    format_row_work,
)


class OcrFindUnreviewedGlyphRowsTests(unittest.TestCase):
    @staticmethod
    def _match(reviewed: bool):
        return SimpleNamespace(style=SimpleNamespace(reviewed=reviewed))

    def test_reviewed_exact_row_needs_no_work(self):
        state = {
            "matches": [self._match(True), self._match(True)],
            "covered_pixels": 123,
            "source_pixels": 123,
            "fully_exact": True,
        }
        work = classify_row_state(1, (0, 36), state)
        self.assertFalse(work.needs_work)
        self.assertEqual(0, work.unreviewed_matches)
        self.assertEqual("page 1 column 0 row 36: unreviewed=0 pixels=exact", format_row_work(work))

    def test_exact_row_with_unreviewed_match_is_reported(self):
        state = {
            "matches": [self._match(True), self._match(False), self._match(False)],
            "covered_pixels": 200,
            "source_pixels": 200,
            "fully_exact": True,
        }
        work = classify_row_state(2, (1, 4), state)
        self.assertTrue(work.needs_work)
        self.assertEqual(2, work.unreviewed_matches)
        self.assertIn("unreviewed=2 pixels=exact", format_row_work(work))

    def test_reviewed_non_exact_row_is_reported(self):
        state = {
            "matches": [self._match(True)],
            "covered_pixels": 197,
            "source_pixels": 203,
            "fully_exact": False,
        }
        work = classify_row_state(3, (2, 9), state)
        self.assertTrue(work.needs_work)
        self.assertEqual(0, work.unreviewed_matches)
        self.assertEqual("page 3 column 2 row 9: unreviewed=0 pixels=197/203", format_row_work(work))

    def test_page_filters(self):
        self.assertEqual(
            [2, 3],
            _selected_pages([1, 2, 3, 4], pages=None, start_page=2, end_page=3),
        )
        self.assertEqual(
            [1, 4],
            _selected_pages([1, 2, 3, 4], pages=[4, 1], start_page=None, end_page=None),
        )
        with self.assertRaisesRegex(ValueError, "pages are not present"):
            _selected_pages([1, 2], pages=[3], start_page=None, end_page=None)


if __name__ == "__main__":
    unittest.main()
