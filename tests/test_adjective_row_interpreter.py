from __future__ import annotations

import unittest

from swedish_wordlist_tools.adjective_row_interpreter import interpret_adjective_row


class AdjectiveRowInterpreterTests(unittest.TestCase):
    def parse(self, lemma: str, text: str, **extra):
        record = {"normaliserat_ord": lemma, "text": text, "upos": "ADJ"}
        record.update(extra)
        slots = interpret_adjective_row(record)
        self.assertIsNotNone(slots)
        return slots

    def test_unlabelled_positive_sequences_share_one_structural_rule(self) -> None:
        cases = (
            ("glad", "+t +a", ("glad", "glatt", "glada")),
            ("blå", "+tt +a", ("blå", "blått", "blåa")),
            ("öm", "+t +ma", ("öm", "ömt", "ömma")),
            ("bebodd", "bebott bebodda", ("bebodd", "bebott", "bebodda")),
            ("perenn", "perent +a", ("perenn", "perent", "perenna")),
            ("obunden", "-bundet -bundna", ("obunden", "obundet", "obundna")),
            ("osäker", "+t -säkra", ("osäker", "osäkert", "osäkra")),
        )
        for lemma, notation, expected in cases:
            with self.subTest(notation=notation):
                slots = self.parse(lemma, notation)
                self.assertEqual(expected, slots.written_forms())
                self.assertEqual("structural_positive_sequence", slots.rule)

    def test_full_unlabelled_sequences_use_slot_order(self) -> None:
        cases = (
            ("god", "gott goda, bättre bäst", ("god", "gott", "goda", "bättre", "bäst")),
            ("dålig", "+t +a, sämre sämst", ("dålig", "dåligt", "dåliga", "sämre", "sämst")),
            ("stor", "+t +a, större störst", ("stor", "stort", "stora", "större", "störst")),
        )
        for lemma, notation, expected in cases:
            with self.subTest(notation=notation):
                slots = self.parse(lemma, notation)
                self.assertEqual(expected, slots.written_forms())
                self.assertEqual("structural_full_adjective_sequence", slots.rule)

    def test_single_operations_are_assigned_by_operation_role(self) -> None:
        neuter = self.parse("dan", "+t")
        self.assertEqual(("dan", "dant"), neuter.written_forms())
        self.assertEqual("neuter_singular", neuter.forms[1].slot)

        explicit = self.parse("förstnämnde", "förstnämnda")
        self.assertEqual(("förstnämnde", "förstnämnda"), explicit.written_forms())
        self.assertEqual("definite_or_plural", explicit.forms[1].slot)

    def test_positive_labels_select_slots_structurally(self) -> None:
        cases = (
            ("kortväxt", "n. +, +a", ("kortväxt", "kortväxta")),
            ("hot", "neutr. +; pl. hotta", ("hot", "hotta")),
            ("fullmäktig", "pl. +e", ("fullmäktig", "fullmäktige")),
            ("främsta", "mask. främste", ("främsta", "främste")),
            (
                "akvamarinblå",
                "-blått, best. och: pl. + el. +a",
                ("akvamarinblå", "akvamarinblått", "akvamarinblåa"),
            ),
            (
                "blå",
                "blått, best. och: pl. blå el. blåa",
                ("blå", "blått", "blåa"),
            ),
        )
        for lemma, notation, expected in cases:
            with self.subTest(notation=notation):
                slots = self.parse(lemma, notation)
                self.assertEqual(expected, slots.written_forms())
                self.assertEqual("structural_labelled_positive_slots", slots.rule)

    def test_labelled_comparison_slots_are_structural(self) -> None:
        cases = (
            ("ringa", "komp. +re, superl. +st", ("ringa", "ringare", "ringast")),
            ("få", "komp. färre, superl. färst", ("få", "färre", "färst")),
            (
                "förnäm",
                "+t +a, komp. +are, superl. +st H +ast",
                ("förnäm", "förnämt", "förnäma", "förnämare", "förnämst", "förnämast"),
            ),
        )
        for lemma, notation, expected in cases:
            with self.subTest(notation=notation):
                slots = self.parse(lemma, notation)
                self.assertEqual(expected, slots.written_forms())
                self.assertEqual("structural_labelled_comparison_slots", slots.rule)

    def test_unlabelled_comparison_alternatives_are_structural(self) -> None:
        slots = self.parse("trång", "+t, trängre H +are, trängst H +ast")
        self.assertEqual(
            ("trång", "trångt", "trängre", "trångare", "trängst", "trångast"),
            slots.written_forms(),
        )
        self.assertEqual("structural_unlabelled_comparison_alternatives", slots.rule)
        self.assertEqual(
            ("comparative", "comparative", "superlative", "superlative"),
            tuple(form.slot for form in slots.forms[2:]),
        )

    def test_unlabelled_alternatives_reuse_same_slot(self) -> None:
        slots = self.parse("bemälde", "bemälda el. bemälta")
        self.assertEqual(("bemälde", "bemälda", "bemälta"), slots.written_forms())
        self.assertTrue(slots.rule.startswith("structural_"))
        self.assertEqual(
            ("definite_or_plural", "definite_or_plural"),
            (slots.forms[1].slot, slots.forms[2].slot),
        )

    def test_partial_labelled_sequence_is_structural(self) -> None:
        slots = self.parse("enda", "ende, vard. superl. endaste")
        self.assertEqual(("enda", "ende", "endaste"), slots.written_forms())
        self.assertEqual("structural_partial_labelled_slots", slots.rule)
        self.assertEqual(
            ("masculine_definite", "superlative"),
            (slots.forms[1].slot, slots.forms[2].slot),
        )

    def test_bare_slot_label_is_structural(self) -> None:
        slots = self.parse("flesta", "best.")
        self.assertEqual(("flesta",), slots.written_forms())
        self.assertEqual("structural_bare_slot_label", slots.rule)
        self.assertEqual("definite_or_plural", slots.forms[0].slot)

    def test_rich_labelled_sequence_is_structural(self) -> None:
        slots = self.parse("liten", "litet, best. lille lilla; pl. små; mindre minst")
        self.assertEqual(
            ("liten", "litet", "lille", "lilla", "små", "mindre", "minst"),
            slots.written_forms(),
        )
        self.assertEqual("structural_full_labelled_slots", slots.rule)
        self.assertEqual(
            (
                "common_singular",
                "neuter_singular",
                "masculine_definite",
                "definite_or_plural",
                "definite_or_plural",
                "comparative",
                "superlative",
            ),
            tuple(form.slot for form in slots.forms),
        )

    def test_usage_restrictions_are_metadata_not_paradigms(self) -> None:
        adenoid = self.parse("adenoid", "n. sing. obest. obrukl., adenoida")
        self.assertEqual(("adenoid", "adenoida"), adenoid.written_forms())
        self.assertEqual("structural_usage_restrictions", adenoid.rule)
        self.assertEqual(("neuter_singular", "uncommon"), (adenoid.restrictions[0].scope, adenoid.restrictions[0].label))

        fadd = self.parse("fadd", "n. sing. obest. undviks:, fadda")
        self.assertEqual(("fadd", "fadda"), fadd.written_forms())
        self.assertEqual("avoided", fadd.restrictions[0].label)

        beige = self.parse("beige", "mest: oböjl., best. och: pl. ibl. beigea")
        self.assertEqual(("beige", "beigea"), beige.written_forms())
        self.assertEqual(("mostly_uninflected", "occasional"), tuple(item.label for item in beige.restrictions))
        self.assertEqual(("beigea",), beige.restrictions[1].forms)

    def test_positive_parallel_branches_are_independent(self) -> None:
        cases = (
            (
                "fasetterad",
                "fasetterat +e _ facetterat +e",
                ("fasetterad", "fasetterat", "fasetterade", "facetterad", "facetterat", "facetterade"),
                {},
            ),
            (
                "hårdflörtad",
                "-flörtat +e _ -flirtat +e",
                ("hårdflörtad", "hårdflörtat", "hårdflörtade", "hårdflirtad", "hårdflirtat", "hårdflirtade"),
                {},
            ),
            (
                "ledsen",
                "ledset ledsna _ lesset lessna",
                ("ledsen", "ledset", "ledsna", "lesset", "lessna"),
                {},
            ),
            (
                "upptuperad",
                "-tuperat +e _ -touperat +e",
                ("upptuperad", "upptuperat", "upptuperade", "upptouperad", "upptouperat", "upptouperade"),
                {"stycke": "upp|tup·er·ad"},
            ),
        )
        for lemma, notation, expected, extra in cases:
            with self.subTest(notation=notation):
                slots = self.parse(lemma, notation, **extra)
                self.assertEqual(expected, slots.written_forms())
                self.assertEqual("structural_parallel_positive_branches", slots.rule)

    def test_more_exotic_parallel_variant_still_falls_back(self) -> None:
        slots = self.parse("sjangdobel", "+t sjangdobla _ +t schangdobla")
        self.assertEqual(("sjangdobel", "sjangdobelt", "sjangdobla", "schangdobel", "schangdobelt", "schangdobla"), slots.written_forms())
        self.assertNotEqual("structural_parallel_positive_branches", slots.rule)


if __name__ == "__main__":
    unittest.main()
