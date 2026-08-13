from __future__ import annotations

import unittest

from swedish_wordlist_tools.classify_next_noun_batch import (
    SALDO_MISSING_ALTERNATIVE_NEUTER_DEFINITE_SINGULAR,
    SALDO_MISSING_ALTERNATIVE_PLURAL,
    SALDO_MISSING_ZERO_PLURAL_DEFINITE,
    SALDO_ZERO_AND_S_PLURAL_DEFINITE_PARADIGM,
    SALDO_ZERO_VS_S_PLURAL_DEFINITE_PARADIGM,
    classify_batch_row,
)


class NextNounBatchRound2Tests(unittest.TestCase):
    def _row(self, lemma: str, notation: str, extra: list[str], missing: list[str]):
        return {
            "upos": "NOUN",
            "lemma": lemma,
            "notation": notation,
            "paradigm_status": "form_set_mismatch",
            "extra_from_saol": extra,
            "missing_from_saol": missing,
        }

    def test_missing_alternative_plural(self) -> None:
        row = self._row(
            "stickprov",
            "+et; pl. + el. +er",
            ["stickprover", "stickprovers", "stickproverna", "stickprovernas"],
            [],
        )
        self.assertEqual(SALDO_MISSING_ALTERNATIVE_PLURAL, classify_batch_row(row)[0])

    def test_missing_zero_plural_definite(self) -> None:
        row = self._row(
            "cigg",
            "+en; pl. + el. +ar",
            ["ciggna", "ciggnas"],
            [],
        )
        self.assertEqual(SALDO_MISSING_ZERO_PLURAL_DEFINITE, classify_batch_row(row)[0])

    def test_zero_and_s_plural_definite(self) -> None:
        row = self._row(
            "backpacker",
            "+n; pl. + H +s",
            ["backpackerna", "backpackernas", "backpackersna", "backpackersnas"],
            ["backpackersen", "backpackersens", "backpackersarna", "backpackersarnas"],
        )
        self.assertEqual(SALDO_ZERO_AND_S_PLURAL_DEFINITE_PARADIGM, classify_batch_row(row)[0])

    def test_zero_vs_s_plural_definite(self) -> None:
        row = self._row(
            "hacker",
            "+n; pl. +",
            ["hackerna", "hackernas"],
            ["hackersen", "hackersens", "hackersarna", "hackersarnas"],
        )
        self.assertEqual(SALDO_ZERO_VS_S_PLURAL_DEFINITE_PARADIGM, classify_batch_row(row)[0])

    def test_missing_alternative_neuter_definite_singular(self) -> None:
        row = self._row(
            "traktat",
            "+en el. +et; pl. +er el. +",
            ["traktatet", "traktatets"],
            [],
        )
        self.assertEqual(
            SALDO_MISSING_ALTERNATIVE_NEUTER_DEFINITE_SINGULAR,
            classify_batch_row(row)[0],
        )


if __name__ == "__main__":
    unittest.main()
