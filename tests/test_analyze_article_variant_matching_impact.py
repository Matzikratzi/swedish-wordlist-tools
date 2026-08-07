from __future__ import annotations

import unittest

from swedish_wordlist_tools.analyze_article_variant_matching_impact import _status


class AnalyzeArticleVariantMatchingImpactTests(unittest.TestCase):
    def test_status_exact(self) -> None:
        analyses = [{"forms": ["foo", "foos"]}]
        self.assertEqual("exact_form_set", _status({"foo", "foos"}, analyses))

    def test_status_mismatch(self) -> None:
        analyses = [{"forms": ["foo", "foos"]}]
        self.assertEqual("form_set_mismatch", _status({"foo", "fooes"}, analyses))


if __name__ == "__main__":
    unittest.main()
