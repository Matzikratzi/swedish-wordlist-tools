from __future__ import annotations

import unittest

from swedish_wordlist_tools.revalidate_direct_forms import (
    canonical_validation_row,
    select_article_variant_match_from_artifacts,
)


class RevalidateArticleVariantsTests(unittest.TestCase):
    def analysis(self, lemma: str, *forms: str) -> dict[str, object]:
        return {
            "id": lemma,
            "lemmas": [lemma],
            "forms": list(forms),
            "upos": "NOUN",
        }

    def test_bankvasen_unions_saldo_analyses_for_both_lemmas(self) -> None:
        record = {
            "normaliserat_ord": "bankväsen",
            "upos": "NOUN",
            "ordkl": "s.",
            "subnr": "5598",
            "homonr": "1",
        }
        first = self.analysis(
            "bankväsen",
            "bankväsen", "bankväsens", "bankväsendet", "bankväsendets",
            "bankväsendena", "bankväsendenas",
        )
        second = self.analysis(
            "bankväsende",
            "bankväsende", "bankväsendes", "bankväsendet", "bankväsendets",
            "bankväsenden", "bankväsendens", "bankväsendena", "bankväsendenas",
        )
        saldo = {"bankväsen": [first], "bankväsende": [second]}
        paradigms = {
            "bankväsen": {
                "bankväsen", "bankväsens", "bankväsendet", "bankväsendets",
                "bankväsendena", "bankväsendenas",
            },
            "bankväsende": {
                "bankväsende", "bankväsendes", "bankväsendet", "bankväsendets",
                "bankväsenden", "bankväsendens", "bankväsendena", "bankväsendenas",
            },
        }
        generated = set().union(*paradigms.values())
        selected = select_article_variant_match_from_artifacts(
            record, saldo, {}, generated, paradigms
        )
        self.assertIsNotNone(selected)
        assert selected is not None
        method, analyses = selected
        self.assertEqual("article_variant_lemmas_same_upos", method)
        row = canonical_validation_row(
            record,
            method,
            analyses,
            generated_forms=generated,
            generator="canonical_artifact",
            variant_lemmas=tuple(paradigms),
        )
        self.assertEqual("exact_form_set", row["status"])
        self.assertEqual(["bankväsen", "bankväsende"], row["saol_variant_lemmas"])
        self.assertEqual([], row["extra_from_saol"])
        self.assertEqual([], row["missing_from_saol"])

    def test_partial_variant_match_is_visible(self) -> None:
        record = {"normaliserat_ord": "x", "upos": "NOUN", "ordkl": "s."}
        saldo = {"x": [self.analysis("x", "x", "xen")]}
        paradigms = {"x": {"x", "xen"}, "y": {"y", "yen"}}
        selected = select_article_variant_match_from_artifacts(
            record, saldo, {}, {"x", "xen", "y", "yen"}, paradigms
        )
        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual("article_variant_lemmas_same_upos_partial", selected[0])


if __name__ == "__main__":
    unittest.main()
