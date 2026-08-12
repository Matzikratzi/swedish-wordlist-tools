from __future__ import annotations

import unittest

from swedish_wordlist_tools.generate_x_routed_shared_forms import generate_rows


class GenerateXRoutedSharedFormsTests(unittest.TestCase):
    def _row_by_source_ord(self, rows, source_ord: str):
        return next(row for row in rows if row["source_ord"] == source_ord)

    def test_hv_noun_uses_printed_variant_as_shared_base(self) -> None:
        records = [
            {"normaliserat_ord":"annektion","ord":"annektion","stycke":"annektion","ordkl":"subst.","text":"+en +er","upos":"NOUN"},
            {"normaliserat_ord":"annektion","ord":"annexion","stycke":"annexion","ordkl":"(hv) <i>+en +er</i>","text":"+en +er","upos":"X"},
        ]
        rows, summary = generate_rows(records)
        self.assertEqual(1, summary["generated_records"])
        row = self._row_by_source_ord(rows, "annexion")
        self.assertEqual("NOUN", row["target_upos"])
        self.assertEqual("annexion", row["routed_lemma"])
        words = {form["written_form"] for form in row["forms"]}
        self.assertTrue({"annexion", "annexionen", "annexioner"} <= words)

    def test_hv_adjective_uses_printed_variant_as_shared_base(self) -> None:
        records = [
            {"normaliserat_ord":"buddistisk","ord":"buddistisk","stycke":"buddistisk","ordkl":"adj.","text":"+t +a","upos":"ADJ"},
            {"normaliserat_ord":"buddistisk","ord":"buddhistisk","stycke":"buddhistisk","ordkl":"(hv) <i>+t +a</i>","text":"+t +a","upos":"X"},
        ]
        rows, summary = generate_rows(records)
        self.assertEqual(1, summary["generated_records"])
        words = {form["written_form"] for form in self._row_by_source_ord(rows, "buddhistisk")["forms"]}
        self.assertTrue({"buddhistisk", "buddhistiskt", "buddhistiska"} <= words)

    def test_hv_verb_uses_printed_variant_as_shared_base(self) -> None:
        records = [
            {"normaliserat_ord":"sjappa","ord":"sjappa","stycke":"sjappa","ordkl":"verb","text":"+de +t","upos":"VERB"},
            {"normaliserat_ord":"sjappa","ord":"schappa","stycke":"schappa","ordkl":"(hv) <i>+de +t</i>","text":"+de +t","upos":"X"},
        ]
        rows, summary = generate_rows(records)
        self.assertEqual(1, summary["generated_records"])
        words = {form["written_form"] for form in self._row_by_source_ord(rows, "schappa")["forms"]}
        self.assertTrue({"schappa", "schappade", "schappat"} <= words)

    def test_mixed_adverb_adjective_is_generated_by_adjective_shared(self) -> None:
        record = {"normaliserat_ord":"ansatsvis","ord":"ansatsvis","stycke":"ansatsvis","ordkl":"adv. och adj. <i>+t +a</i>","text":"+t +a","upos":"X"}
        rows, summary = generate_rows([record])
        self.assertEqual(1, summary["generated_records"])
        self.assertTrue({"ansatsvis", "ansatsvist", "ansatsvisa"} <= {f["written_form"] for f in rows[0]["forms"]})

    def test_hv_comparative_relation_is_explicit_form_not_new_paradigm(self) -> None:
        records = [
            {"normaliserat_ord":"få","ord":"få","stycke":"få","ordkl":"adj.","text":"färre färst","upos":"ADJ"},
            {"normaliserat_ord":"få","ord":"färre","stycke":"färre","ordkl":"(hv) <i>komp.</i>","text":"komp.","upos":"X"},
        ]
        rows, summary = generate_rows(records)
        self.assertEqual(1, summary["generated_records"])
        self.assertEqual(1, summary["relation_only_records"])
        row = self._row_by_source_ord(rows, "färre")
        self.assertEqual([("comparative", "färre")], [(f["slot"], f["written_form"]) for f in row["forms"]])

    def test_hv_noun_explicit_definite_plural_replacement_is_safe(self) -> None:
        records = [
            {"normaliserat_ord":"kyrkobesökare","ord":"kyrkobesökare","stycke":"kyrkobesökare","ordkl":"subst.","text":"+n; pl. +, best. pl. -besökarna","upos":"NOUN"},
            {"normaliserat_ord":"kyrkobesökare","ord":"kyrkbesökare","stycke":"kyrkbesökare","ordkl":"(hv) <i>+n; pl. +, best. pl. -besökarna</i>","text":"+n; pl. +, best. pl. -besökarna","upos":"X"},
        ]
        rows, summary = generate_rows(records)
        self.assertEqual(0, summary["failed_records"])
        self.assertTrue({"kyrkbesökare", "kyrkbesökaren", "kyrkbesökarna"} <= {f["written_form"] for f in self._row_by_source_ord(rows, "kyrkbesökare")["forms"]})

    def test_split_replacement_payload_is_normalized_for_routed_noun(self) -> None:
        records = [
            {"normaliserat_ord":"sidoroder","ord":"sidoroder","stycke":"sidoroder","ordkl":"subst.","text":"-rodret; pl. +, best. pl.- rodren","upos":"NOUN"},
            {"normaliserat_ord":"sidoroder","ord":"sidroder","stycke":"sidroder","ordkl":"(hv) <i>-rodret; pl. +, best. pl.- rodren</i>","text":"-rodret; pl. +, best. pl.- rodren","upos":"X"},
        ]
        rows, summary = generate_rows(records)
        self.assertEqual(0, summary["failed_records"])
        self.assertTrue({"sidroder", "sidrodret", "sidrodren"} <= {f["written_form"] for f in self._row_by_source_ord(rows, "sidroder")["forms"]})

    def test_textless_homonym_forms_are_preserved_in_resolved_class(self) -> None:
        records = [
            {"normaliserat_ord":"få","homonr":"1","ord":"få","ordkl":"v.","text":"fick konjunktiv: finge, fått, pres. får","upos":"VERB"},
            {"normaliserat_ord":"få","homonr":"2","ord":"få","ordkl":"adj.","text":"komp. färre, superl. färst","upos":"ADJ"},
            {"normaliserat_ord":"få","homonr":"0","ord":"fick","ordkl":"(hv)","text":None,"upos":"X"},
            {"normaliserat_ord":"få","homonr":"0","ord":"färst","ordkl":"(hv)","text":None,"upos":"X"},
        ]
        rows, summary = generate_rows(records)
        self.assertEqual(2, summary["generated_records"])
        self.assertEqual(0, summary["failed_records"])
        fick = self._row_by_source_ord(rows, "fick")
        farst = self._row_by_source_ord(rows, "färst")
        self.assertEqual("VERB", fick["target_upos"])
        self.assertEqual("ADJ", farst["target_upos"])
        self.assertEqual(["fick"], [f["written_form"] for f in fick["forms"]])
        self.assertEqual(["färst"], [f["written_form"] for f in farst["forms"]])
        self.assertTrue(fick["relation_only"])
        self.assertTrue(farst["relation_only"])

    def test_textless_pronoun_hv_is_direct_form_without_pronoun_generator(self) -> None:
        records = [
            {"normaliserat_ord":"jag","ord":"jag","ordkl":"pron.","text":"obj. mig","upos":"PRON"},
            {"normaliserat_ord":"jag","ord":"mig","ordkl":"(hv)","text":None,"upos":"X"},
        ]
        rows, summary = generate_rows(records)
        self.assertEqual(1, summary["generated_records"])
        self.assertEqual("PRON", rows[0]["target_upos"])
        self.assertEqual("mig", rows[0]["forms"][0]["written_form"])


if __name__ == "__main__":
    unittest.main()
