import unittest

from swedish_wordlist_tools.ocr_review_five_rows_glyphs_html import (
    defect_packet,
    is_defective,
    neighbour,
    packet_positions,
    render_five_row_html,
    row_url,
    window_positions,
)


class FiveRowGlyphReviewTests(unittest.TestCase):
    def test_packet_crosses_column_boundary_and_moves_five_at_a_time(self):
        positions = [(0, 48), (0, 49), (1, 0), (1, 1), (1, 2), (1, 3), (1, 4)]
        self.assertEqual(
            packet_positions(positions, (1, 0)),
            [(0, 48), (0, 49), (1, 0), (1, 1), (1, 2)],
        )
        self.assertEqual(window_positions(positions, (1, 0)), packet_positions(positions, (1, 0)))
        self.assertEqual(neighbour(positions, (1, 0), -1), (0, 49))
        self.assertEqual(neighbour(positions, (0, 49), 1), (1, 0))

    def test_defect_packet_is_lazy_and_skips_exact_rows(self):
        positions = [(0, i) for i in range(10)]
        defective = {1, 3, 4, 7, 9}
        calls = []

        def state_for(position):
            calls.append(position)
            row = position[1]
            return {"covered_pixels": 9 if row in defective else 10, "source_pixels": 10}

        self.assertEqual(
            defect_packet(positions, (0, 0), state_for),
            [(0, 1), (0, 3), (0, 4), (0, 7), (0, 9)],
        )
        self.assertEqual(calls[-1], (0, 9))
        self.assertTrue(is_defective({"covered_pixels": 9, "source_pixels": 10}))
        self.assertFalse(is_defective({"covered_pixels": 10, "source_pixels": 10}))

    def test_backward_defect_packet_keeps_reading_order(self):
        positions = [(0, i) for i in range(10)]
        defective = {0, 2, 4, 6, 8}

        def state_for(position):
            row = position[1]
            return {"covered_pixels": 0 if row in defective else 1, "source_pixels": 1}

        self.assertEqual(
            defect_packet(positions, (0, 8), state_for, direction=-1),
            [(0, 0), (0, 2), (0, 4), (0, 6), (0, 8)],
        )

    def test_render_has_packet_navigation_fast_switching_and_defect_mode(self):
        positions = [(0, i) for i in range(10)]
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
        self.assertIn("← Fem föregående", html)
        self.assertIn("Fem nästa →", html)
        self.assertIn("☐ Bara defekta", html)
        self.assertIn("↻ Räkna om paketet", html)
        self.assertIn("Byte mellan de fem använder redan analyserade rader", html)
        self.assertIn(row_url((0, 1), anchor=(0, 0)), html)
        self.assertIn(row_url((0, 5)), html)
        self.assertIn("ArrowLeft", html)
        self.assertIn("ArrowRight", html)

    def test_render_defect_mode_preserves_mode_for_row_switches(self):
        positions = [(0, i) for i in range(8)]
        states = []
        for i in (1, 2, 4, 6, 7):
            states.append(
                {
                    "page": 1,
                    "column": 0,
                    "row": i,
                    "covered_pixels": 9,
                    "source_pixels": 10,
                    "removed_neighbor_pixels": 0,
                    "text": f"row{i}",
                    "crop_width": 20,
                    "crop_height": 10,
                    "baseline": 7,
                    "image": "data:image/png;base64,AA==",
                    "source_ink_points": [[1, 1]],
                    "items": [],
                }
            )
        html = render_five_row_html(
            states, (0, 4), positions, mode="defects", anchor=(0, 1)
        )
        self.assertIn("☑ Bara defekta", html)
        self.assertIn("Visar endast rader med okända pixlar", html)
        self.assertIn(row_url((0, 4), mode="defects", anchor=(0, 1)), html)


if __name__ == "__main__":
    unittest.main()
