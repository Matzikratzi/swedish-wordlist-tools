from __future__ import annotations

import unittest

from swedish_wordlist_tools.adjective_form_provenance import (
    form_provenance,
    form_provenance_details,
)


class AdjectiveFormProvenanceTests(unittest.TestCase):
    def test_unchanged_neuter_with_plural_suffix_is_append(self) -> None:
        details = form_provenance_details(
            written_form="otäckta",
            lemma="otäckt",
            slot="definite_or_plural",
            notation="n. +, +a",
        )
        self.assertEqual("append", details.kind)
        self.assertEqual("+a", details.source_token)

    def test_replace_tail_keeps_exact_source_token(self) -> None:
        details = form_provenance_details(
            written_form="förstfött",
            lemma="förstfödd",
            slot="neuter_singular",
            notation="-fött +a",
        )
        self.assertEqual("replace_tail", details.kind)
        self.assertEqual("-fött", details.source_token)

    def test_parallel_alternative_common_form_is_explicit(self) -> None:
        details = form_provenance_details(
            written_form="facetterad",
            lemma="fasetterad",
            slot="common_singular",
            notation="fasetterat +e _ facetterat +e",
        )
        self.assertEqual("explicit", details.kind)
        self.assertEqual("facetterat +e", details.source_token)

    def test_parallel_replacement_alternative_common_form_is_explicit(self) -> None:
        details = form_provenance_details(
            written_form="hårdflirtad",
            lemma="hårdflörtad",
            slot="common_singular",
            notation="-flörtat +e _ -flirtat +e",
        )
        self.assertEqual("explicit", details.kind)
        self.assertEqual("-flirtat +e", details.source_token)

    def test_backward_compatible_kind_helper(self) -> None:
        self.assertEqual(
            "append",
            form_provenance(
                written_form="glada",
                lemma="glad",
                slot="definite_or_plural",
                notation="+t +a",
            ),
        )


if __name__ == "__main__":
    unittest.main()
