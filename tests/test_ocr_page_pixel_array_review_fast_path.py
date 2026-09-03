import unittest
from unittest.mock import patch

from swedish_wordlist_tools import ocr_review_page_pixel_array_glyphs_html as review


class PagePixelArrayReviewFastPathTests(unittest.TestCase):
    def test_exact_row_never_runs_two_row_ownership(self):
        exact = {"fully_exact": True}
        with (
            patch.object(review, "_load_owned_row_state", return_value=exact) as load,
            patch.object(review, "_ensure_known_glyph_ownership") as refine,
            patch.object(review, "add_neighbor_row_raster", side_effect=lambda _context, state, **_kw: state),
        ):
            result = review.load_review_state_pixel_array({}, (1, 7), object())

        self.assertIs(result, exact)
        load.assert_called_once()
        refine.assert_not_called()

    def test_defective_row_reanalyses_only_when_ownership_changes(self):
        defective = {"fully_exact": False}
        repaired = {"fully_exact": True}
        with (
            patch.object(review, "_load_owned_row_state", side_effect=[defective, repaired]) as load,
            patch.object(review, "_neighbor_pairs", return_value={(1, 6), (1, 7)}) as pairs,
            patch.object(review, "_ensure_known_glyph_ownership", return_value=True) as refine,
            patch.object(review, "add_neighbor_row_raster", side_effect=lambda _context, state, **_kw: state),
        ):
            result = review.load_review_state_pixel_array({}, (1, 7), object())

        self.assertIs(result, repaired)
        self.assertEqual(load.call_count, 2)
        pairs.assert_called_once_with({}, (1, 7))
        refine.assert_called_once()

    def test_defective_row_is_not_reanalysed_when_ownership_does_not_change(self):
        defective = {"fully_exact": False}
        with (
            patch.object(review, "_load_owned_row_state", return_value=defective) as load,
            patch.object(review, "_neighbor_pairs", return_value={(2, 3)}),
            patch.object(review, "_ensure_known_glyph_ownership", return_value=False) as refine,
            patch.object(review, "add_neighbor_row_raster", side_effect=lambda _context, state, **_kw: state),
        ):
            result = review.load_review_state_pixel_array({}, (2, 3), object())

        self.assertIs(result, defective)
        load.assert_called_once()
        refine.assert_called_once()


if __name__ == "__main__":
    unittest.main()
