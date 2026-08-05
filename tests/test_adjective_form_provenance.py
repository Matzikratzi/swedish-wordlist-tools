from __future__ import annotations

import unittest

from swedish_wordlist_tools.adjective_form_provenance import form_provenance


class AdjectiveFormProvenanceTests(unittest.TestCase):
    def test_unchanged_neuter_with_plural_suffix_is_append(self) -> None:
        self.assertEqual(
            "append",
            form_provenance(
                written_form="otäckta",
                lemma="otäckt",
                slot="definite_or_plural",
                notation="n. +, +a",
            ),
        )

    def test_parallel_alternative_common_form_is_explicit(self) -> None:
        self.assertEqual(
            "explicit",
            form_provenance(
                written_form="facetterad",
                lemma="fasetterad",
                slot="common_singular",
                notation="fasetterat +e _ facetterat +e",
            ),
        )

    def test_parallel_replacement_alternative_common_form_is_explicit(self) -> None:
        self.assertEqual(
            "explicit",
            form_provenance(
                written_form="hårdflirtad",
                lemma="hårdflörtad",
                slot="common_singular",
                notation="-flörtat +e _ -flirtat +e",
            ),
        )


if __name__ == "__main__":
    unittest.main()
