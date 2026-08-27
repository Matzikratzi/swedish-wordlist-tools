import unittest
from pathlib import Path

from swedish_wordlist_tools.ocr_glyph_matcher import GlyphModel, analyse, exact_sequence_cover, load_facit


class GlyphMatcherTests(unittest.TestCase):
    def test_perfect_q_infers_baseline_without_seed(self):
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

        result = analyse(source_pixels, 6, 11, models, expected="q")

        self.assertEqual(result["baseline"], 7)
        self.assertTrue(result["fully_exact"])
        self.assertEqual([r["label"] for r in result["exact_sequence_cover"]], ["q"])
        self.assertEqual(result["exact_sequence_cover"][0]["baseline"], 7)

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
        result = analyse(source_pixels, width, height, models, expected="qigong")

        self.assertTrue(result["fully_exact"])
        self.assertEqual([row["label"] for row in result["exact_sequence_cover"]], labels)
        self.assertTrue(all(row["style"] == "bold" for row in result["exact_sequence_cover"]))
        self.assertTrue(all(row["baseline"] == 11 for row in result["exact_sequence_cover"]))

    def test_exact_cover_rejects_local_baseline_shift(self):
        a = GlyphModel("a", "bold", frozenset({(0, -1), (0, 0)}), 1)
        b = GlyphModel("b", "bold", frozenset({(0, -1), (1, 0)}), 1)
        ink = {(0, 2), (0, 3), (2, 1), (3, 2)}
        cover = exact_sequence_cover(ink, 4, 4, [a, b], "ab")
        self.assertIsNone(cover)

    def test_exact_cover_accepts_multichar_model(self):
        tt = GlyphModel("tt", "bold", frozenset({(0, -1), (0, 0), (1, -1), (1, 0)}), 1)
        ink = {(0, 1), (0, 2), (1, 1), (1, 2)}
        cover = exact_sequence_cover(ink, 2, 3, [tt], "tt")
        self.assertIsNotNone(cover)
        self.assertEqual([m.label for m in cover], ["tt"])
        self.assertEqual(cover[0].baseline, 2)


if __name__ == "__main__":
    unittest.main()
