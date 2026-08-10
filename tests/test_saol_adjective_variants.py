from __future__ import annotations

import unittest

from swedish_wordlist_tools.adjective_variant_interpreter import interpret_adjective_row
from swedish_wordlist_tools.saol_adjective_variants import prepare_adjective_variant_records


class SaolAdjectiveVariantTests(unittest.TestCase):
    def test_hv_row_supplies_parallel_variant_base(self) -> None:
        records = [
            {
                "normaliserat_ord": "sjangdobel",
                "homonr": "1",
                "ordkl": "(hv)",
                "stycke": "schangdobel",
                "text": "(null)",
                "upos": "X",
                "ord": "schangdobel",
            },
            {
                "normaliserat_ord": "sjangdobel",
                "homonr": "1",
                "ordkl": "adj. +t sjangdobla ...",
                "stycke": "sjangd·obel",
                "text": "+t sjangdobla _ +t schangdobla",
                "upos": "ADJ",
                "ord": "sjangd·obel",
            },
        ]
        prepared = prepare_adjective_variant_records(records)
        adjective = prepared[1]
        self.assertEqual("schangdobel", adjective["_saol_alternative_lemma"])
        self.assertEqual("matching_hv_row", adjective["_saol_variant_evidence"])

        slots = interpret_adjective_row(adjective)
        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual("structural_parallel_explicit_variant", slots.rule)
        self.assertEqual(
            (
                "sjangdobel",
                "sjangdobelt",
                "sjangdobla",
                "schangdobel",
                "schangdobelt",
                "schangdobla",
            ),
            slots.written_forms(),
        )

    def test_hv_evidence_is_not_attached_without_two_parallel_branches(self) -> None:
        records = [
            {
                "normaliserat_ord": "foo",
                "ordkl": "(hv)",
                "text": "(null)",
                "ord": "fo",
            },
            {
                "normaliserat_ord": "foo",
                "ordkl": "adj. +t +a",
                "text": "+t +a",
                "upos": "ADJ",
                "ord": "foo",
            },
        ]
        prepared = prepare_adjective_variant_records(records)
        self.assertNotIn("_saol_alternative_lemma", prepared[1])


if __name__ == "__main__":
    unittest.main()
