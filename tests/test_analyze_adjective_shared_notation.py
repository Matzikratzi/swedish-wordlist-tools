from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_adjective_shared_notation import analyze_records


class AnalyzeAdjectiveSharedNotationTests(unittest.TestCase):
    def test_audits_only_uninterpreted_adjectives(self) -> None:
        report = analyze_records(
            [
                {
                    "normaliserat_ord": "glad",
                    "upos": "ADJ",
                    "text": "+t +a",
                    "stycke": "glad",
                },
                {
                    "normaliserat_ord": "fyrtioförsta",
                    "upos": "ADJ",
                    "text": "mask. fyrti(o)förste",
                    "stycke": "fyr·tio|första",
                },
                {
                    "normaliserat_ord": "okänd",
                    "upos": "ADJ",
                    "text": "kommentar: +t +a",
                    "stycke": "okänd",
                },
                {
                    "normaliserat_ord": "springa",
                    "upos": "VERB",
                    "text": "sprang",
                },
            ]
        )
        self.assertEqual(3, report["adjective_records"])
        self.assertEqual(1, report["already_interpreted_records"])
        self.assertEqual(2, report["remaining_records"])
        self.assertEqual(2, report["remaining_tokenizable_by_shared_layer"])
        self.assertEqual(2, report["remaining_structured_by_shared_layer"])
        self.assertEqual(1, report["remaining_with_optional_form_tokens"])
        self.assertEqual({"fyrti(o)förste": 1}, report["optional_token_counts"])

    def test_rejects_unparsed_nonnotation_text(self) -> None:
        report = analyze_records(
            [
                {
                    "normaliserat_ord": "test",
                    "upos": "ADJ",
                    "text": "ord med fri prosa",
                    "stycke": "test",
                }
            ]
        )
        self.assertEqual(0, report["remaining_structured_by_shared_layer"])


if __name__ == "__main__":
    unittest.main()
