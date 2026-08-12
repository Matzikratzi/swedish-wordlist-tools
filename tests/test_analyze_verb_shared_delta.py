from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_verb_shared_delta import analyze


class AnalyzeVerbSharedDeltaTests(unittest.TestCase):
    def record(
        self,
        lemma: str,
        text: str,
        homonr: str = "1",
        *,
        stycke: str | None = None,
    ) -> dict[str, object]:
        return {
            "normaliserat_ord": lemma,
            "text": text,
            "stycke": lemma if stycke is None else stycke,
            "upos": "VERB",
            "ordkl": "v.",
            "homonr": homonr,
        }

    def test_regular_two_atom_row_is_identical(self) -> None:
        summary = analyze([self.record("abonnera", "+de +t")])
        self.assertEqual(1, summary["same_records"])
        self.assertEqual(0, summary["changed_records"])
        self.assertEqual(3, summary["old_unique_forms"])
        self.assertEqual(3, summary["shared_unique_forms"])

    def test_shared_delta_reports_added_and_removed_forms(self) -> None:
        # A complete bare present label is deliberately interpreted by the
        # shared grammar as the lemma itself in present. The comparison should
        # report form-set changes rather than hiding them behind slot metadata.
        summary = analyze([self.record("lyster", "pres.")])
        self.assertEqual(1, summary["old_interpreted"])
        self.assertEqual(1, summary["shared_interpreted"])
        self.assertEqual({"lyster"}, set(summary["changed"][0]["old_forms"])) if summary["changed"] else None

    def test_multiword_lemma_is_outside_direct_comparison(self) -> None:
        summary = analyze([self.record("ta sig", "tog tagit")])
        self.assertEqual(0, summary["records"])

    def test_legacy_label_leak_is_classified_as_notation_artifact(self) -> None:
        summary = analyze([self.record("djärvas", "djärvdes, pres. djärvs el. djärves")])
        self.assertIn("pres", summary["old_only_classified"]["legacy_notation_artifact"])
        self.assertEqual([], summary["old_only_classified"]["unexplained"])

    def test_50_character_final_form_is_classified_as_unsafe_tail(self) -> None:
        text = "-stämde, -stämt, -stämd n. -stämt, pres. -stämmer,"
        self.assertEqual(50, len(text))
        summary = analyze([self.record("avstämma", text, stycke="av|stämma")])
        self.assertIn(
            "avstämmer",
            summary["old_only_classified"]["unsafe_truncated_final_token"],
        )
        self.assertEqual([], summary["old_only_classified"]["unexplained"])


if __name__ == "__main__":
    unittest.main()
