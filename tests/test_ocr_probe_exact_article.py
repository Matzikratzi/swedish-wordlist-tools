from __future__ import annotations

import unittest

from swedish_wordlist_tools.ocr_glyph_matcher import Match
from swedish_wordlist_tools.ocr_probe_exact_article import build_exact_article


class ExactArticleProbeTests(unittest.TestCase):
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
    def row(cls, specs, *, fully_exact=True):
        matches = [cls.match(label, style, x, width) for label, style, x, width in specs]
        ink = set().union(*(match.pixels for match in matches)) if matches else set()
        return {"matches": matches, "ink": ink, "fully_exact": fully_exact}

    def test_numbered_explanations_remain_in_same_article_across_rows(self) -> None:
        rows = [
            self.row([
                ("a", "bold", 0, 2), ("b", "bold", 2, 2),
                ("[", "roman", 8, 1), ("x", "roman", 9, 2), ("]", "roman", 11, 1),
                ("s", "roman", 16, 2), (".", "roman", 18, 1),
                ("~", "italic", 23, 2), ("n", "italic", 25, 2), (";", "italic", 27, 1),
            ]),
            self.row([
                ("p", "roman", 0, 2), ("l", "roman", 2, 2), (".", "roman", 4, 1),
                ("~", "italic", 9, 2),
                ("1", "roman", 15, 1),
                ("(", "roman", 20, 1), ("å", "roman", 21, 2), ("l", "roman", 23, 2),
                ("d", "roman", 25, 2), (".", "roman", 27, 1), (")", "roman", 28, 1),
                ("e", "roman", 33, 2), ("t", "roman", 35, 2), ("i", "roman", 37, 1),
                ("o", "roman", 38, 2), ("p", "roman", 40, 2), ("i", "roman", 42, 1),
                ("e", "roman", 43, 2), ("r", "roman", 45, 2),
                ("2", "roman", 50, 1), ("e", "roman", 55, 2), ("n", "roman", 57, 2),
            ]),
            self.row([("k", "roman", 0, 2), ("a", "roman", 2, 2), ("t", "roman", 4, 2), ("t", "roman", 6, 2)]),
            self.row([("c", "bold", 0, 2), ("d", "bold", 2, 2), ("s", "roman", 8, 2), (".", "roman", 10, 1)]),
        ]

        article = build_exact_article(rows)

        self.assertEqual(article["rows_consumed"], 3)
        self.assertEqual(article["stycke"], "ab")
        self.assertEqual(article["ordkl"], "[x] s. <i>~n;</i> pl. <i>~</i>")
        self.assertEqual(article["text"], "~n; pl. ~")
        self.assertEqual(article["boundary"], "numbered-explanation")
        self.assertEqual(article["remainder"], "1 (åld.) etiopier 2 en katt")
        self.assertEqual(
            article["markup"],
            "<b>ab</b> [x] s. <i>~n;</i> pl. <i>~</i> 1 (åld.) etiopier 2 en katt",
        )

    def test_explanation_marker_ends_text_but_not_article(self) -> None:
        rows = [
            self.row([
                ("a", "bold", 0, 2), ("s", "roman", 6, 2), (".", "roman", 8, 1),
                ("~", "italic", 13, 2), ("n", "italic", 15, 2),
                ("¤", "italic", 21, 1), ("e", "roman", 26, 2), ("n", "roman", 28, 2),
            ]),
            self.row([("f", "roman", 0, 2), ("i", "roman", 2, 1), ("s", "roman", 3, 2), ("k", "roman", 5, 2)]),
            self.row([("b", "bold", 0, 2), ("s", "roman", 6, 2), (".", "roman", 8, 1)]),
        ]
        article = build_exact_article(rows)
        self.assertEqual(article["rows_consumed"], 2)
        self.assertEqual(article["text"], "~n")
        self.assertEqual(article["boundary"], "explanation-marker")
        self.assertEqual(article["remainder"], "¤ en fisk")

    def test_requires_bold_headword_on_first_row(self) -> None:
        with self.assertRaisesRegex(ValueError, "bold headword"):
            build_exact_article([self.row([("k", "roman", 0, 2)])])


if __name__ == "__main__":
    unittest.main()
