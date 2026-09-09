from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_build_cluster_glyph import (
    _enclosed_white,
    _orthogonal_contacts,
    build_cluster_entry,
    find_cluster_placements,
)


def entry(model_id: str, label: str, pixels: set[tuple[int, int]]) -> dict:
    return {
        "label": label,
        "role": "unknown",
        "pixels_relative_to_baseline": [list(p) for p in sorted(pixels)],
        "sources": [],
        "reviewed": True,
        "model_id": model_id,
    }


class ClusterGlyphTests(unittest.TestCase):
    def test_two_contacts_can_create_enclosed_white_hole(self) -> None:
        # Left side plus top/bottom arms.
        left = frozenset({(0, 0), (1, 0), (0, 1), (0, 2), (1, 2)})
        # Right vertical stroke, shifted to x=2.
        right = frozenset({(2, 0), (2, 1), (2, 2)})
        union = frozenset(left | right)

        self.assertEqual(2, _orthogonal_contacts(left, right))
        self.assertEqual(frozenset({(1, 1)}), _enclosed_white(union))

    def test_finds_unique_same_baseline_cluster_offset(self) -> None:
        left = entry("g000001", "f", {(0, 0), (1, 0), (0, 1), (0, 2), (1, 2)})
        right = entry("g000002", "r", {(0, 0), (0, 1), (0, 2)})

        placements = find_cluster_placements(
            [left],
            [right],
            contacts=2,
            min_dx=0,
            max_dx=4,
        )

        self.assertEqual(1, len(placements))
        placement = placements[0]
        self.assertEqual(2, placement.dx)
        self.assertEqual(8, len(placement.pixels))
        self.assertEqual(frozenset({(1, 1)}), placement.enclosed_white)

    def test_cluster_entry_preserves_shared_role(self) -> None:
        left = entry("g000001", "f", {(0, 0), (1, 0), (0, 1), (0, 2), (1, 2)})
        right = entry("g000002", "r", {(0, 0), (0, 1), (0, 2)})
        left["role"] = "bold"
        right["role"] = "bold"
        placement = find_cluster_placements([left], [right], min_dx=2, max_dx=2)[0]

        cluster = build_cluster_entry("fr", placement, [left, right])

        self.assertEqual("bold", cluster["role"])

    def test_cluster_entry_falls_back_to_unknown_for_mixed_roles(self) -> None:
        left = entry("g000001", "f", {(0, 0), (1, 0), (0, 1), (0, 2), (1, 2)})
        right = entry("g000002", "r", {(0, 0), (0, 1), (0, 2)})
        left["role"] = "bold"
        right["role"] = "roman"
        placement = find_cluster_placements([left], [right], min_dx=2, max_dx=2)[0]

        cluster = build_cluster_entry("fr", placement, [left, right])

        self.assertEqual("unknown", cluster["role"])

    def test_cluster_entry_preserves_shared_style(self) -> None:
        left = entry("g000001", "f", {(0, 0), (1, 0), (0, 1), (0, 2), (1, 2)})
        right = entry("g000002", "r", {(0, 0), (0, 1), (0, 2)})
        left["style"] = "unknown"
        right["style"] = "unknown"
        placement = find_cluster_placements([left], [right], min_dx=2, max_dx=2)[0]

        cluster = build_cluster_entry("fr", placement, [left, right])

        self.assertEqual("fr", cluster["label"])
        self.assertEqual("unknown", cluster["style"])
        self.assertEqual("g000003", cluster["model_id"])
        self.assertTrue(cluster["reviewed"])
        self.assertEqual(8, len(cluster["pixels_relative_to_baseline"]))


if __name__ == "__main__":
    unittest.main()
