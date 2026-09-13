import unittest

from swedish_wordlist_tools.ocr_baseline_up import BaselineMatch
from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel
from swedish_wordlist_tools.ocr_row_directional import _candidate_explains_left_ink_to_baseline


class FirstGlyphBaselineLeftInkTest(unittest.TestCase):
    def _candidate(self) -> BaselineMatch:
        model = GlyphModel(
            label="short",
            style="test",
            pixels=frozenset({(0, -2), (1, -2), (2, -2)}),
            sources=1,
        )
        return BaselineMatch(
            model=model,
            tx=10,
            baseline=12,
            pixels=frozenset({(10, 10), (11, 10), (12, 10)}),
            discovered_y=10,
        )

    def test_accepts_candidate_when_left_region_to_baseline_is_explained(self) -> None:
        candidate = self._candidate()
        black = set(candidate.pixels)

        self.assertTrue(_candidate_explains_left_ink_to_baseline(candidate, black))

    def test_rejects_candidate_when_unexplained_ink_lies_left_to_baseline(self) -> None:
        candidate = self._candidate()
        black = set(candidate.pixels)
        black.add((9, 12))

        self.assertFalse(_candidate_explains_left_ink_to_baseline(candidate, black))

    def test_ignores_unexplained_ink_to_the_right_of_trigger_front(self) -> None:
        candidate = self._candidate()
        black = set(candidate.pixels)
        black.add((11, 12))

        self.assertTrue(_candidate_explains_left_ink_to_baseline(candidate, black))


if __name__ == "__main__":
    unittest.main()
