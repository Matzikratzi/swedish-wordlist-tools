from __future__ import annotations

import unittest

from swedish_wordlist_tools.generate_verb_forms import generated_row


class GenerateVerbFormsTests(unittest.TestCase):
    def test_generates_structured_shared_forms(self) -> None:
        row = generated_row(
            {
                "normaliserat_ord": "handha",
                "homonr": "1",
                "text": "-hade, -haft, -havd -haft -havda, pres. -har",
                "stycke": "hand|ha",
                "upos": "VERB",
                "ordkl": "v.",
            }
        )
        self.assertIsNotNone(row)
        assert row is not None
        by_slot = {}
        for form in row["forms"]:
            by_slot.setdefault(form["slot"], []).append(form["written_form"])
        self.assertEqual(["handhade"], by_slot["preterite"])
        self.assertEqual(["handhaft"], by_slot["supine"])
        self.assertEqual(["handhavd"], by_slot["perfect_participle_common"])
        self.assertEqual(["handhaft"], by_slot["perfect_participle_neuter"])
        self.assertEqual(["handhavda"], by_slot["perfect_participle_plural"])
        self.assertEqual(["handhar"], by_slot["present"])

    def test_truncated_row_keeps_only_safe_visible_forms(self) -> None:
        text = "tog, tagit, tagen taget tagna, pres. tar el. åld."
        self.assertEqual(49, len(text))
        row = generated_row(
            {
                "normaliserat_ord": "ta",
                "homonr": "1",
                "text": text,
                "stycke": "ta",
                "upos": "VERB",
                "ordkl": "v.",
            }
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertTrue(row["source_truncated"])
        words = {form["written_form"] for form in row["forms"]}
        self.assertIn("tar", words)
        self.assertNotIn("tager", words)
        self.assertNotIn("tag", words)


if __name__ == "__main__":
    unittest.main()
