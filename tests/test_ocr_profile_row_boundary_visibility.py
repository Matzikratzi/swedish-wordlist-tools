from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_profile_automaton_batch import _profile_point_is_visible


class ProfileRowBoundaryVisibilityTest(unittest.TestCase):
    def test_exact_left_profile_point_is_visible(self) -> None:
        self.assertTrue(_profile_point_is_visible(106, 106))

    def test_hidden_profile_point_cannot_be_borrowed_from_other_row(self) -> None:
        # The candidate expects its own left edge at x=109, but unexplained ink
        # at x=106 is still the live frontier on that raster row.  Under the
        # non-interleaving-row invariant this candidate cannot own x=109 yet.
        self.assertFalse(_profile_point_is_visible(106, 109))

    def test_missing_or_past_profile_point_is_not_visible(self) -> None:
        self.assertFalse(_profile_point_is_visible(None, 109))
        self.assertFalse(_profile_point_is_visible(110, 109))


if __name__ == "__main__":
    unittest.main()
