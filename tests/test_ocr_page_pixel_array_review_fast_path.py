import unittest
from unittest.mock import Mock, patch

from swedish_wordlist_tools import ocr_review_page_pixel_array_glyphs_html as review


class PagePixelArrayReviewFastPathTests(unittest.TestCase):
    def test_exact_row_never_runs_two_row_ownership(self):
        exact = {"fully_exact": True, "pixel_owner_row_revision": 0}
        context = {"pixel_owner_row_revisions": {}}
        with (
            patch.object(review, "_load_owned_row_state", return_value=exact) as load,
            patch.object(review, "_ensure_known_glyph_ownership") as refine,
            patch.object(review, "add_neighbor_row_raster", side_effect=lambda _context, state, **_kw: state),
        ):
            result = review.load_review_state_pixel_array(context, (1, 7), object())

        self.assertIs(result, exact)
        load.assert_called_once()
        refine.assert_not_called()

    def test_defective_row_reanalyses_when_ownership_changes(self):
        defective = {"fully_exact": False, "pixel_owner_row_revision": 0}
        repaired = {"fully_exact": True, "pixel_owner_row_revision": 1}
        context = {"pixel_owner_row_revisions": {(1, 7): 1}}
        with (
            patch.object(review, "_load_owned_row_state", side_effect=[defective, repaired]) as load,
            patch.object(review, "_neighbor_pairs", return_value={(1, 6), (1, 7)}) as pairs,
            patch.object(review, "_ensure_known_glyph_ownership", return_value=True) as refine,
            patch.object(review, "add_neighbor_row_raster", side_effect=lambda _context, state, **_kw: state),
        ):
            result = review.load_review_state_pixel_array(context, (1, 7), object())

        self.assertIs(result, repaired)
        self.assertEqual(load.call_count, 2)
        pairs.assert_called_once_with(context, (1, 7))
        refine.assert_called_once()

    def test_defective_row_reanalyses_if_its_parallel_owner_revision_changed(self):
        defective = {"fully_exact": False, "pixel_owner_row_revision": 0}
        refreshed = {"fully_exact": False, "pixel_owner_row_revision": 1}
        context = {"pixel_owner_row_revisions": {(2, 3): 1}}
        with (
            patch.object(review, "_load_owned_row_state", side_effect=[defective, refreshed]) as load,
            patch.object(review, "_neighbor_pairs", return_value={(2, 3)}),
            patch.object(review, "_ensure_known_glyph_ownership", return_value=False),
            patch.object(review, "add_neighbor_row_raster", side_effect=lambda _context, state, **_kw: state),
        ):
            result = review.load_review_state_pixel_array(context, (2, 3), object())

        self.assertIs(result, refreshed)
        self.assertEqual(load.call_count, 2)

    def test_packet_refreshes_only_row_whose_ownership_changed(self):
        row27_stale = {"fully_exact": False, "pixel_owner_row_revision": 0}
        row27_fresh = {"fully_exact": True, "pixel_owner_row_revision": 1}
        row29_cached = {"fully_exact": True, "pixel_owner_row_revision": 0}
        fake_cache = Mock()
        fake_cache.get.return_value = row27_fresh
        positions = [(1, 27), (1, 29)]
        original_states = [row27_stale, row29_cached]
        old_context = review._current_pixel_context
        try:
            review._current_pixel_context = {
                "pixel_owner_row_revisions": {(1, 27): 1, (1, 28): 1}
            }
            with patch.object(review, "_original_cache_get_many", return_value=original_states):
                result = review._get_many_owner_revision_safe(fake_cache, positions)
        finally:
            review._current_pixel_context = old_context

        self.assertEqual(result, [row27_fresh, row29_cached])
        fake_cache.invalidate.assert_called_once_with((1, 27))
        fake_cache.get.assert_called_once_with((1, 27))


if __name__ == "__main__":
    unittest.main()
