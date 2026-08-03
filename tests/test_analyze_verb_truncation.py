from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_verb_slots import (
    _external_lookup_candidate,
    _truncation_kind,
)


class AnalyzeVerbTruncationTests(unittest.TestCase):
    def record(self, text: str, ordkl: str) -> dict[str, str]:
        return {"text": text, "ordkl": ordkl, "upos": "VERB"}

    def test_marks_mid_word_present_form_for_external_lookup(self) -> None:
        record = self.record(
            "sjöng, sjungit, sjungen sjunget sjungna, pres. sju",
            "v. <i>sjöng, sjungit, s...</i>",
        )
        self.assertTrue(_external_lookup_candidate(record))
        self.assertEqual("external_lookup_candidate", _truncation_kind(record))

    def test_does_not_mark_normal_compact_notation(self) -> None:
        record = self.record("+de +t", "v. <i>+de +t</i>")
        self.assertFalse(_external_lookup_candidate(record))
        self.assertIsNone(_truncation_kind(record))

    def test_separates_ellipsis_when_text_is_still_usable(self) -> None:
        record = self.record(
            "-gjorde, -gjort, -gjord n. -gjort, pres. -gör",
            "v. <i>-gjorde, -gjort, ...</i>",
        )
        self.assertFalse(_external_lookup_candidate(record))
        self.assertEqual("ellipsis_but_text_usable", _truncation_kind(record))

    def test_requires_source_ellipsis(self) -> None:
        record = self.record(
            "sjöng, sjungit, sjungen sjunget sjungna, pres. sju",
            "v.",
        )
        self.assertFalse(_external_lookup_candidate(record))
        self.assertIsNone(_truncation_kind(record))


if __name__ == "__main__":
    unittest.main()
