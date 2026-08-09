from __future__ import annotations

import unittest

from swedish_wordlist_tools.refresh_noun_validation import MODULES


class RefreshNounValidationTests(unittest.TestCase):
    def test_rebuilds_noun_artifact_before_validation(self) -> None:
        self.assertEqual(
            (
                "swedish_wordlist_tools.generate_noun_forms",
                "swedish_wordlist_tools.revalidate_direct_forms",
                "swedish_wordlist_tools.rebaseline_noun_validation",
                "swedish_wordlist_tools.analyze_remaining_noun_notations",
                "swedish_wordlist_tools.analyze_remaining_noun_provenance",
            ),
            MODULES,
        )


if __name__ == "__main__":
    unittest.main()
