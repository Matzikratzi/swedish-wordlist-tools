import unittest

from swedish_wordlist_tools.inflect import generate_entry, generate_forms


class DetachedSuffixRowTests(unittest.TestCase):
    def test_rejects_one_letter_lemma_with_unmarked_suffix_tokens(self) -> None:
        self.assertIsNone(generate_forms("a", "et n na"))
        self.assertIsNone(
            generate_entry(
                {
                    "normaliserat_ord": "a",
                    "text": "et n na",
                    "upos": "NOUN",
                }
            )
        )

    def test_keeps_normal_explicit_irregular_forms(self) -> None:
        self.assertEqual(
            generate_forms("gå", "går gick gått"),
            ("gå", "går", "gick", "gått"),
        )


if __name__ == "__main__":
    unittest.main()
