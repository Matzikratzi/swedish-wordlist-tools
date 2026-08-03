from __future__ import annotations

import unittest

from swedish_wordlist_tools.lexeme_slots import SlotForm, build_lexeme_slots
from swedish_wordlist_tools.saldo_verb_fallback import (
    add_saldo_attested_forms,
    exact_saldo_verb_analyses,
)


class SaldoVerbFallbackTests(unittest.TestCase):
    def slots(self):
        return build_lexeme_slots(
            lemma="skriva",
            upos="VERB",
            notation="skrev, skrivit",
            forms=(
                SlotForm("infinitive", "skriva", "lemma"),
                SlotForm("preterite", "skrev", "skrev"),
                SlotForm("supine", "skrivit", "skrivit"),
            ),
        )

    def test_adds_only_new_attested_forms_with_provenance(self) -> None:
        analyses = [
            {
                "id": "skriva..vb.1",
                "upos": "VERB",
                "lemmas": {"skriva"},
                "forms": {"skriva", "skrev", "skrivit", "skriver", "skrivs"},
            }
        ]
        enriched = add_saldo_attested_forms(self.slots(), analyses)
        self.assertEqual(
            {"skriver", "skrivs"},
            set(enriched.forms_for("saldo_attested")),
        )
        saldo_forms = [
            form for form in enriched.forms if form.slot == "saldo_attested"
        ]
        self.assertTrue(all(form.provenance == "saldo" for form in saldo_forms))
        self.assertTrue(
            all(form.provenance_detail == "skriva..vb.1" for form in saldo_forms)
        )
        self.assertEqual("row", next(enriched.iter_slot("preterite")).provenance)

    def test_unions_exact_homonymous_verb_analyses(self) -> None:
        analyses = [
            {
                "id": "falla..vb.1",
                "upos": "VERB",
                "lemmas": {"falla"},
                "forms": {"faller", "föll"},
            },
            {
                "id": "falla..vb.2",
                "upos": "VERB",
                "lemmas": {"falla"},
                "forms": {"falla", "fall"},
            },
            {
                "id": "falla..nn.1",
                "upos": "NOUN",
                "lemmas": {"falla"},
                "forms": {"fallan"},
            },
        ]
        self.assertEqual(
            2,
            len(exact_saldo_verb_analyses("falla", analyses)),
        )

    def test_does_not_import_affix_forms(self) -> None:
        analyses = [
            {
                "id": "skriva..vb.1",
                "upos": "VERB",
                "lemmas": {"skriva"},
                "forms": {"skriv-", "skriver"},
            }
        ]
        enriched = add_saldo_attested_forms(self.slots(), analyses)
        self.assertEqual(("skriver",), enriched.forms_for("saldo_attested"))


if __name__ == "__main__":
    unittest.main()
