from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_glyph_matcher import Match
from swedish_wordlist_tools.ocr_probe_exact_article import build_exact_article


class LeadingInflectionLabelTests(unittest.TestCase):
    @staticmethod
    def match(label: str, style: str, x: int, width: int = 1) -> Match:
        return Match(
            label=label,
            style=style,
            x=x,
            baseline=7,
            pixels=frozenset((x + dx, 7) for dx in range(width)),
            model_pixels=width,
            sources=1,
        )

    @classmethod
    def row(cls, specs):
        matches = [cls.match(label, style, x, width) for label, style, x, width in specs]
        ink = set().union(*(match.pixels for match in matches)) if matches else set()
        return {"matches": matches, "ink": ink, "fully_exact": True}

    def test_plural_label_before_first_italic_belongs_to_text(self) -> None:
        row = self.row([
            ("a", "bold", 0, 2),
            ("s", "roman", 6, 2), (".", "roman", 8, 1),
            ("p", "roman", 13, 2), ("l", "roman", 15, 1), (".", "roman", 16, 1),
            ("~", "italic", 21, 2),
        ])
        article = build_exact_article([row])
        self.assertEqual(article["ordkl"], "s. pl. <i>~</i>")
        self.assertEqual(article["text"], "pl. ~")

    def test_best_label_before_first_italic_belongs_to_text(self) -> None:
        row = self.row([
            ("a", "bold", 0, 2),
            ("s", "roman", 6, 2), (".", "roman", 8, 1),
            ("b", "roman", 13, 2), ("e", "roman", 15, 2), ("s", "roman", 17, 2),
            ("t", "roman", 19, 2), (".", "roman", 21, 1),
            ("~", "italic", 26, 2),
        ])
        article = build_exact_article([row])
        self.assertEqual(article["ordkl"], "s. best. <i>~</i>")
        self.assertEqual(article["text"], "best. ~")

    def test_part_of_speech_label_does_not_move_into_text(self) -> None:
        row = self.row([
            ("a", "bold", 0, 2),
            ("s", "roman", 6, 2), (".", "roman", 8, 1),
            ("~", "italic", 13, 2),
        ])
        article = build_exact_article([row])
        self.assertEqual(article["text"], "~")


if __name__ == "__main__":
    unittest.main()
