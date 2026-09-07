from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_glyph_matcher import Match
from swedish_wordlist_tools.ocr_probe_exact_article import build_exact_article


class ExactArticleWordClassBoundaryTests(unittest.TestCase):
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
        ink = set().union(*(match.pixels for match in matches))
        return {"matches": matches, "ink": ink, "fully_exact": True}

    def test_aber_text_starts_after_word_class_not_at_first_italic(self) -> None:
        row = self.row([
            ("a", "bold", 0, 1), ("b", "bold", 1, 1), ("e", "bold", 2, 1), ("r", "bold", 3, 1),
            ("[", "roman", 8, 1), ("a", "roman", 9, 1), ("'", "roman", 10, 1),
            ("b", "roman", 11, 1), ("e", "roman", 12, 1), ("r", "roman", 13, 1), ("]", "roman", 14, 1),
            ("s", "roman", 19, 1), (".", "roman", 20, 1), (";", "roman", 21, 1),
            ("p", "roman", 26, 1), ("l", "roman", 27, 1), (".", "roman", 28, 1),
            ("~", "italic", 33, 1),
            ("¤", "roman", 38, 1),
            ("s", "roman", 43, 1),
        ])

        article = build_exact_article([row])

        self.assertEqual(article["stycke"], "aber")
        self.assertEqual(article["text"], "pl. ~")
        self.assertEqual(article["boundary"], "explanation-marker")
        self.assertEqual(article["remainder"], "¤ s")

    def test_text_may_begin_in_roman_without_any_italic_glyph(self) -> None:
        row = self.row([
            ("x", "bold", 0, 1),
            ("s", "roman", 5, 1), (".", "roman", 6, 1),
            ("p", "roman", 11, 1), ("l", "roman", 12, 1), (".", "roman", 13, 1),
            ("o", "roman", 18, 1), ("b", "roman", 19, 1), ("ö", "roman", 20, 1),
            ("j", "roman", 21, 1), ("l", "roman", 22, 1), (".", "roman", 23, 1),
        ])

        article = build_exact_article([row])

        self.assertEqual(article["text"], "pl. oböjl.")


if __name__ == "__main__":
    unittest.main()
