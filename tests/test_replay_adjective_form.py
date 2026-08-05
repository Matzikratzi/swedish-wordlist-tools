from __future__ import annotations

import unittest

from swedish_wordlist_tools.replay_adjective_form import replay_generated_form


class ReplayAdjectiveFormTests(unittest.TestCase):
    def test_replays_bar_based_replace_tail(self) -> None:
        result = replay_generated_form(
            lemma="förstfödd",
            stycke="först|född",
            written_form="förstfött",
            slot="neuter_singular",
            provenance="replace_tail",
            source_token="-fött",
        )
        self.assertEqual("match", result.status)
        self.assertEqual("förstfött", result.replayed_form)

    def test_replays_append(self) -> None:
        result = replay_generated_form(
            lemma="bakåtböjd",
            stycke="bakåt|böjd",
            written_form="bakåtböjda",
            slot="definite_or_plural",
            provenance="append",
            source_token="+a",
        )
        self.assertEqual("match", result.status)
        self.assertEqual("bakåtböjda", result.replayed_form)

    def test_detects_mismatch(self) -> None:
        result = replay_generated_form(
            lemma="glad",
            stycke="glad",
            written_form="gladt",
            slot="neuter_singular",
            provenance="append",
            source_token="+t",
        )
        self.assertEqual("mismatch", result.status)
        self.assertEqual("glatt", result.replayed_form)


if __name__ == "__main__":
    unittest.main()
