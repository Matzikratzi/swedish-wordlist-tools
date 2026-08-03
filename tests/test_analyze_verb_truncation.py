from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_verb_slots import (
    _external_lookup_candidate,
    _truncation_kind,
)


class AnalyzeVerbTruncationTests(unittest.TestCase):
    def record(self, text: str, ordkl: str) -> dict[str, str]:
        return {"text": text, "ordkl": ordkl, "upos": "VERB"}

    def test_marks_text_at_observed_hard_cap(self) -> None:
        text = "sjöng, sjungit, sjungen sjunget sjungna, pres. sju"
        self.assertEqual(50, len(text))
        record = self.record(text, "v. <i>sjöng, sjungit, s...</i>")
        self.assertTrue(_external_lookup_candidate(record))
        self.assertEqual("text_at_hard_cap", _truncation_kind(record))

    def test_does_not_mark_normal_compact_notation(self) -> None:
        record = self.record("+de +t", "v. <i>+de +t</i>")
        self.assertFalse(_external_lookup_candidate(record))
        self.assertIsNone(_truncation_kind(record))

    def test_ordkl_ellipsis_is_not_text_truncation_evidence(self) -> None:
        record = self.record(
            "-gjorde, -gjort, -gjord n. -gjort, pres. -gör",
            "v. <i>-gjorde, -gjort, ...</i>",
        )
        self.assertLess(len(record["text"]), 50)
        self.assertFalse(_external_lookup_candidate(record))
        self.assertEqual(
            "ordkl_ellipsis_but_text_below_cap",
            _truncation_kind(record),
        )

    def test_marks_length_50_even_without_ordkl_ellipsis(self) -> None:
        text = "försjönk, försjunkit, försjunken försjunket försju"
        self.assertEqual(50, len(text))
        record = self.record(text, "v.")
        self.assertTrue(_external_lookup_candidate(record))
        self.assertEqual("text_at_hard_cap", _truncation_kind(record))


if __name__ == "__main__":
    unittest.main()
