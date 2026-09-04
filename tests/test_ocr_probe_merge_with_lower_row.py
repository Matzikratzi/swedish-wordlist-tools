import unittest

from swedish_wordlist_tools.ocr_page_pixel_array import PagePixelArray
from swedish_wordlist_tools.ocr_probe_merge_with_lower_row import apply_merge_down, probe_zero_match_merge_down


class _Match:
    def __init__(self, label):
        self.label = label


class MergeDownProbeTests(unittest.TestCase):
    def _context(self, fully_exact=True):
        owners = PagePixelArray(width=6, height=8, data=bytearray(48))
        upper = owners.row_code(0); lower = owners.row_code(1)
        owners.data[1 * 6 + 2] = upper
        owners.data[2 * 6 + 2] = upper
        owners.data[4 * 6 + 2] = lower
        owners.data[5 * 6 + 2] = lower

        def analyse(_crop, _models, *, threshold):
            return {
                "fully_exact": fully_exact,
                "selected": [_Match("i")] if fully_exact else [],
                "baseline": 5,
                "covered_pixels": 4 if fully_exact else 0,
                "source_pixels": 4,
            }

        return {
            "pixel_owners": owners,
            "threshold": 210,
            "analyse_row_exact": analyse,
            "known_glyph_ownership_lock": __import__("threading").Lock(),
            "pixel_owner_revision": 0,
            "pixel_owner_row_revisions": {},
        }

    def test_exact_single_baseline_merge_is_applied(self):
        context = self._context(True)
        upper_state = {"column": 0, "row": 0, "source_pixels": 2, "matches": [], "crop_box": (0, 0, 6, 4)}
        lower_state = {"column": 0, "row": 1, "source_pixels": 2, "matches": [], "crop_box": (0, 3, 6, 8)}
        proof = probe_zero_match_merge_down(context, upper_state, lower_state, [])
        self.assertIsNotNone(proof)
        self.assertEqual(proof["labels"], "i")
        self.assertEqual(apply_merge_down(context, proof), 2)
        lower = context["pixel_owners"].row_code(1)
        self.assertEqual(context["pixel_owners"].value(2, 1), lower)
        self.assertEqual(context["pixel_owners"].value(2, 2), lower)
        self.assertEqual(context["pixel_owner_row_revisions"], {(0, 0): 1, (0, 1): 1})

    def test_non_exact_merge_does_not_produce_proof(self):
        context = self._context(False)
        upper_state = {"column": 0, "row": 0, "source_pixels": 2, "matches": [], "crop_box": (0, 0, 6, 4)}
        lower_state = {"column": 0, "row": 1, "source_pixels": 2, "matches": [], "crop_box": (0, 3, 6, 8)}
        self.assertIsNone(probe_zero_match_merge_down(context, upper_state, lower_state, []))
        upper = context["pixel_owners"].row_code(0)
        self.assertEqual(context["pixel_owners"].value(2, 1), upper)


if __name__ == "__main__":
    unittest.main()
