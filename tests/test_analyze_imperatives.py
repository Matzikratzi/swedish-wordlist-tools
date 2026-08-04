from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from swedish_wordlist_tools.analyze_imperatives import (
    _is_imperative_label,
    explicit_saol_imperatives,
    generate_imperative,
    read_saldo_form_labels,
)
from swedish_wordlist_tools.lexeme_slots import SlotForm, build_lexeme_slots


class AnalyzeImperativesTests(unittest.TestCase):
    def slots(self, lemma: str, preterite: str):
        return build_lexeme_slots(
            lemma=lemma,
            upos="VERB",
            notation="",
            forms=(SlotForm("preterite", preterite, "test"),),
        )

    def test_class1_keeps_infinitive(self) -> None:
        self.assertEqual(
            ("tala", "class1_preterite_ade"),
            generate_imperative("tala", self.slots("tala", "talade")),
        )

    def test_other_a_verb_drops_final_a(self) -> None:
        self.assertEqual(
            ("skriv", "drop_final_a"),
            generate_imperative("skriva", self.slots("skriva", "skrev")),
        )

    def test_non_a_infinitive_is_unchanged(self) -> None:
        self.assertEqual(("gå", "non_a_infinitive"), generate_imperative("gå", None))

    def test_multiword_lemma_is_not_generated(self) -> None:
        self.assertEqual(
            (None, "multiword_lemma"),
            generate_imperative("skriva in", self.slots("skriva in", "skrev in")),
        )

    def test_extracts_complete_explicit_imperative(self) -> None:
        record = {
            "normaliserat_ord": "skriva",
            "text": "skrev, skrivit, pres. skriver, imper. skriv",
        }
        self.assertEqual(("skriv",), explicit_saol_imperatives(record))

    def test_keeps_complete_alternative_before_hard_cap_fragment(self) -> None:
        text = "+de +t, pres. sparar el. spar, imper. spara el. sp"
        self.assertEqual(50, len(text))
        record = {"normaliserat_ord": "spara", "text": text}
        self.assertEqual(("spara",), explicit_saol_imperatives(record))

    def test_drops_only_explicit_imperative_fragment_at_hard_cap(self) -> None:
        text = "skrev, skrivit, pres. skriver, imper. sk".ljust(50, "r")
        self.assertEqual(50, len(text))
        record = {"normaliserat_ord": "skriva", "text": text}
        self.assertEqual((), explicit_saol_imperatives(record))

    def test_recognises_common_imperative_msd_spellings(self) -> None:
        for label in ("VB.IMP.ACT", "vb_imper", "imperativ aktiv", "imperative"):
            with self.subTest(label=label):
                self.assertTrue(_is_imperative_label(label))
        self.assertFalse(_is_imperative_label("VB.PRS.ACT"))

    def test_reads_written_form_with_msd_from_lmf_style_saldo(self) -> None:
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<LexicalResource>
  <LexicalEntry id="skriva..vb.1">
    <Lemma><FormRepresentation><feat att="writtenForm" val="skriva"/></FormRepresentation></Lemma>
    <WordForm>
      <FormRepresentation>
        <feat att="writtenForm" val="skriv"/>
        <feat att="msd" val="VB.IMP.ACT"/>
      </FormRepresentation>
    </WordForm>
    <WordForm>
      <FormRepresentation>
        <feat att="writtenForm" val="skriver"/>
        <feat att="msd" val="VB.PRS.ACT"/>
      </FormRepresentation>
    </WordForm>
  </LexicalEntry>
</LexicalResource>
"""
        handle = tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", suffix=".xml", delete=False
        )
        with handle:
            handle.write(xml)
        path = Path(handle.name)
        self.addCleanup(path.unlink, missing_ok=True)

        saldo, labels = read_saldo_form_labels(path)

        self.assertEqual({"VB.IMP.ACT"}, saldo["skriva"]["skriv"])
        self.assertEqual({"VB.PRS.ACT"}, saldo["skriva"]["skriver"])
        self.assertEqual(1, labels["VB.IMP.ACT"])


if __name__ == "__main__":
    unittest.main()
