from __future__ import annotations

import unittest

from swedish_wordlist_tools.saol_notation import split_alternative_branches
from swedish_wordlist_tools.saol_source_policy import is_truncated_inflection_source
from swedish_wordlist_tools.verb_truncated_shared import assign_truncated_verb_branch


class VerbTruncatedSharedTests(unittest.TestCase):
    def test_49_character_source_keeps_complete_final_form_atom(self) -> None:
        # At 49 characters the final token is complete. The row is still
        # potentially truncated after that token, but the token itself is safe.
        text = "tog tagit pres. tar".ljust(49)
        self.assertEqual(49, len(text))
        self.assertTrue(is_truncated_inflection_source({"text": text}))
        branches = split_alternative_branches(text)
        self.assertEqual(1, len(branches))
        assigned = assign_truncated_verb_branch(branches[0].tokens)
        self.assertIsNotNone(assigned)
        assert assigned is not None
        self.assertEqual("present", assigned[-1].slot)
        self.assertEqual("tar", assigned[-1].token)

    def test_50_character_source_drops_untrusted_final_token(self) -> None:
        # The final visible token may itself be cut at the 50-character cap.
        # Tokenization therefore removes it before shared prefix recovery.
        prefix = "tog tagit pres. tar "
        text = prefix + ("x" * (50 - len(prefix)))
        self.assertEqual(50, len(text))
        self.assertTrue(is_truncated_inflection_source({"text": text}))
        branches = split_alternative_branches(text)
        self.assertEqual(1, len(branches))
        self.assertNotIn("x", " ".join(branches[0].tokens))
        assigned = assign_truncated_verb_branch(branches[0].tokens)
        self.assertIsNotNone(assigned)
        assert assigned is not None
        self.assertEqual("present", assigned[-1].slot)
        self.assertEqual("tar", assigned[-1].token)

    def test_label_only_prefix_is_not_recovered_from_truncated_source(self) -> None:
        # Complete notation may use bare ``pres.`` to mean lemma-as-present,
        # but on a truncated source the following form may simply be missing.
        branches = split_alternative_branches("pres.")
        self.assertEqual(1, len(branches))
        self.assertIsNone(assign_truncated_verb_branch(branches[0].tokens))

    def test_ta_49_character_export_recovers_only_evidenced_prefix(self) -> None:
        text = "tog, tagit, tagen taget tagna, pres. tar el. åld."
        self.assertEqual(49, len(text))
        branches = split_alternative_branches(text)
        assigned = assign_truncated_verb_branch(branches[0].tokens)
        self.assertIsNotNone(assigned)
        assert assigned is not None
        self.assertEqual("present", assigned[-1].slot)
        self.assertEqual("tar", assigned[-1].token)
        # Nothing invents the continuation 'tager, imper. ta ...'.
        self.assertNotIn("tager", tuple(item.token for item in assigned))
        self.assertNotIn("imperative", tuple(item.slot for item in assigned))


if __name__ == "__main__":
    unittest.main()
