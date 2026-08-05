from __future__ import annotations

import unittest

from swedish_wordlist_tools.saol_notation import apply_form_operation, parse_form_operation


class SaolNotationOverlapTests(unittest.TestCase):
    def replace(self, base: str, token: str) -> str | None:
        operation = parse_form_operation(token)
        self.assertIsNotNone(operation)
        assert operation is not None
        return apply_form_operation(
            base,
            operation,
            replace_tail=lambda word, tail: word[: word.rfind(tail[0])] + tail,
        )

    def test_longest_overlap_avoids_duplicated_word_parts(self) -> None:
        cases = {
            ("barntillåten", "-tillåtet"): "barntillåtet",
            ("barntillåten", "-tillåtna"): "barntillåtna",
            ("lättvättad", "-tvättat"): "lättvättat",
            ("otillåten", "-tillåtet"): "otillåtet",
            ("uppoppad", "-poppat"): "uppoppat",
            ("uppumpad", "-pumpat"): "uppumpat",
        }
        for (base, token), expected in cases.items():
            with self.subTest(base=base, token=token):
                self.assertEqual(expected, self.replace(base, token))

    def test_overlap_keeps_already_correct_fallbacks(self) -> None:
        cases = {
            ("fulladdad", "-laddat"): "fulladdat",
            ("lossliten", "-slitna"): "losslitna",
            ("lättrogen", "-trogna"): "lättrogna",
            ("webbaserad", "-baserat"): "webbaserat",
        }
        for (base, token), expected in cases.items():
            with self.subTest(base=base, token=token):
                self.assertEqual(expected, self.replace(base, token))


if __name__ == "__main__":
    unittest.main()
