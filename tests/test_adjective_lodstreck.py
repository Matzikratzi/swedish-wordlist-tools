from __future__ import annotations

import unittest

from swedish_wordlist_tools.adjective_slots import interpret_simple_adjective_slots


class AdjectiveLodstreckTests(unittest.TestCase):
    def parse(self, lemma: str, stycke: str, text: str) -> tuple[str, ...]:
        slots = interpret_simple_adjective_slots(
            {
                "normaliserat_ord": lemma,
                "stycke": stycke,
                "text": text,
                "upos": "ADJ",
            }
        )
        self.assertIsNotNone(slots)
        return slots.written_forms()

    def test_replaces_the_final_compound_part(self) -> None:
        self.assertEqual(
            ("alkoholrelaterad", "alkoholrelaterat", "alkoholrelaterade"),
            self.parse("alkoholrelaterad", "alkohol|relaterad", "-relaterat +e"),
        )
        self.assertEqual(
            ("andtruten", "andtrutet", "andtrutna"),
            self.parse("andtruten", "and|truten", "-trutet -trutna"),
        )
        self.assertEqual(
            ("angelägen", "angeläget", "angelägna"),
            self.parse("angelägen", "an|gelägen", "-geläget -gelägna"),
        )

    def test_strips_homonym_markup_before_the_bar(self) -> None:
        self.assertEqual(
            ("arbetsrelaterad", "arbetsrelaterat", "arbetsrelaterade"),
            self.parse(
                "arbetsrelaterad",
                "<sup>1</sup>arbets|relaterad",
                "-relaterat +e",
            ),
        )


if __name__ == "__main__":
    unittest.main()
