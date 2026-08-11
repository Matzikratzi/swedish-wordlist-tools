from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_noun_shared_coverage import (
    analyze,
    branch_path,
    fallback_reason,
)
from swedish_wordlist_tools.saol_notation import split_alternative_branches


class AnalyzeNounSharedCoverageTests(unittest.TestCase):
    def _tokens(self, text: str) -> tuple[str, ...]:
        branches = split_alternative_branches(text)
        self.assertEqual(1, len(branches))
        return branches[0].tokens

    def test_classifies_independent_shared_paths(self) -> None:
        noun = {"ordkl": "s."}
        self.assertEqual("shared_labelled", branch_path(noun, self._tokens("pl. +ar")))
        self.assertEqual(
            "shared_unlabelled_atoms",
            branch_path(noun, self._tokens("+en +ar")),
        )
        self.assertEqual(
            "shared_unlabelled_atoms",
            branch_path(noun, self._tokens("brodern bröder")),
        )
        self.assertEqual("structural_uninflected", branch_path(noun, self._tokens("oböjl.")))

    def test_relative_and_explicit_atoms_can_mix_in_one_shared_sequence(self) -> None:
        noun = {"ordkl": "s."}
        self.assertEqual(
            "shared_unlabelled_atoms",
            branch_path(noun, self._tokens("+en bröder")),
        )
        self.assertEqual(
            "shared_unlabelled_atoms",
            branch_path(noun, self._tokens("brodern +ar")),
        )

    def test_generic_colon_editorial_label_is_shared(self) -> None:
        noun = {"ordkl": "s."}
        self.assertEqual(
            "shared_unlabelled_atoms",
            branch_path(noun, self._tokens("+en okändmarkör: +ar")),
        )

    def test_truncated_branch_uses_shared_prefix_instead_of_legacy(self) -> None:
        noun = {"ordkl": "s.", "text": "x" * 50}
        self.assertEqual(
            "shared_truncated_partial",
            branch_path(noun, self._tokens("+en; pl. +ar, best. pl.")),
        )

    def test_fallback_reason_is_only_for_unrecoverable_or_complete_unknown_syntax(self) -> None:
        tokens = self._tokens("+en gen. +ar")
        self.assertEqual(
            "remaining_syntax",
            fallback_reason({"text": "+en gen. +ar"}, tokens),
        )
        self.assertEqual(
            "truncated_without_recoverable_prefix",
            fallback_reason({"text": "x" * 50}, tokens),
        )

    def test_truncated_record_is_counted_before_branch_classification(self) -> None:
        second_text = "+en; pl. +ar, best. pl." + " " * 27
        self.assertEqual(50, len(second_text))
        summary = analyze(
            [
                {
                    "upos": "NOUN",
                    "normaliserat_ord": "x",
                    "homonr": "1",
                    "subnr": 1,
                    "text": "x" * 50,
                    "ordkl": "s.",
                },
                {
                    "upos": "NOUN",
                    "normaliserat_ord": "y",
                    "homonr": "1",
                    "subnr": 2,
                    "text": second_text,
                    "ordkl": "s.",
                },
            ]
        )
        self.assertEqual(2, summary["truncated_records"])
        self.assertEqual(1, summary["truncated_records_without_branches"])
        self.assertEqual("x", summary["truncated_without_branches"][0]["lemma"])


if __name__ == "__main__":
    unittest.main()
