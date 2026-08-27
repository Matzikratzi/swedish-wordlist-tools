import unittest
from pathlib import Path

from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel, analyse, load_facit


class GlyphMatcherTests(unittest.TestCase):
    def test_perfect_q_infers_baseline_without_seed(self):
        # Shape taken from the real bold q regression case, but expressed in the
        # facit's coordinate system: x normalized to the left edge, y relative to
        # support baseline. In the source raster the true baseline is y=7 and the
        # descender continues to y=10.
        source_pixels = {
            (2, 0), (3, 0), (4, 0), (5, 0),
            (1, 1), (2, 1), (3, 1), (4, 1), (5, 1),
            (0, 2), (1, 2), (4, 2), (5, 2),
            (0, 3), (1, 3), (4, 3), (5, 3),
            (0, 4), (1, 4), (4, 4), (5, 4),
            (0, 5), (1, 5), (4, 5), (5, 5),
            (1, 6), (2, 6), (3, 6), (4, 6), (5, 6),
            (1, 7), (2, 7), (3, 7), (4, 7), (5, 7),
            (4, 8), (5, 8), (4, 9), (5, 9), (4, 10), (5, 10),
        }
        true_baseline = 7
        model_pixels = frozenset((x, y - true_baseline) for x, y in source_pixels)
        models = [GlyphModel(label="q", style="bold", pixels=model_pixels, sources=2)]

        result = analyse(source_pixels, 6, 11, models)

        self.assertEqual(result["baseline"], 7)
        self.assertEqual(result["baseline_votes"], {7: 41})
        self.assertEqual(
            result["selected_exact"],
            [
                {
                    "label": "q",
                    "style": "bold",
                    "x": 0,
                    "baseline": 7,
                    "pixels": 41,
                    "sources": 2,
                    "score": 1681.0,
                }
            ],
        )

    def test_qigong_is_six_exact_bold_glyphs_on_one_baseline(self):
        facit = Path(__file__).resolve().parents[1] / "glyphs" / "saol14-manual-glyph-facit.json"
        models = load_facit(facit)
        by_label = {(m.label, m.style): m for m in models}

        labels = ["q", "i", "g", "o", "n", "g"]
        xs = [0, 8, 13, 21, 30, 38]
        baseline = 11
        source_pixels = set()
        for label, x0 in zip(labels, xs):
            model = by_label[(label, "bold")]
            source_pixels.update((x0 + x, baseline + y) for x, y in model.pixels)

        width = max(x for x, _ in source_pixels) + 1
        height = max(y for _, y in source_pixels) + 1
        result = analyse(source_pixels, width, height, models)

        self.assertEqual(result["baseline"], 11)
        self.assertEqual([row["label"] for row in result["selected_exact"]], labels)
        self.assertTrue(all(row["style"] == "bold" for row in result["selected_exact"]))
        self.assertTrue(all(row["baseline"] == 11 for row in result["selected_exact"]))
        self.assertEqual(result["fuzzy_diagnostics"], [])


if __name__ == "__main__":
    unittest.main()
