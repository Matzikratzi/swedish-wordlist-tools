import unittest

from swedish_wordlist_tools.ocr_review_five_rows_glyphs_html import (
    neighbour,
    render_five_row_html,
    row_url,
    window_positions,
)


class FiveRowGlyphReviewTests(unittest.TestCase):
    def test_window_crosses_column_boundary(self):
        positions = [(0, 48), (0, 49), (1, 0), (1, 1), (1, 2), (1, 3)]
        self.assertEqual(
            window_positions(positions, (1, 0)),
            [(0, 48), (0, 49), (1, 0), (1, 1), (1, 2)],
        )
        self.assertEqual(neighbour(positions, (1, 0), -1), (0, 49))
        self.assertEqual(neighbour(positions, (0, 49), 1), (1, 0))

    def test_render_has_five_context_rows_navigation_and_recompute(self):
        positions = [(0, i) for i in range(5)]
        states = []
        for i in range(5):
            states.append(
                {
                    "page": 1,
                    "column": 0,
                    "row": i,
                    "covered_pixels": 10 + i,
                    "source_pixels": 12 + i,
                    "removed_neighbor_pixels": 0,
                    "text": f"row{i}",
                    "crop_width": 20,
                    "crop_height": 10,
                    "baseline": 7,
                    "image": "data:image/png;base64,AA==",
                    "source_ink_points": [[1, 1], [2, 2]],
                    "items": [],
                }
            )
        html = render_five_row_html(states, (0, 2), positions)
        self.assertEqual(html.count('class="rowcard'), 5)
        self.assertIn("← Föregående", html)
        self.assertIn("Nästa →", html)
        self.assertIn("↻ Räkna om raderna", html)
        self.assertIn("alla fem visade rader om automatiskt", html)
        self.assertIn(row_url((0, 1)), html)
        self.assertIn(row_url((0, 3)), html)
        self.assertIn("ArrowLeft", html)
        self.assertIn("ArrowRight", html)


if __name__ == "__main__":
    unittest.main()
