from __future__ import annotations

import unittest

from swedish_wordlist_tools.materialize_saol_relations import materialize


class MaterializeSaolRelationsTests(unittest.TestCase):
    def test_materializes_article_headings_and_reference(self) -> None:
        rows = [
            {"normaliserat_ord":"akne","homonr":"1","ordkl":"s. <i>+n</i>","urspr_lopnr":10,"subnr":10,"text":"+n","upos":"NOUN","ord":"akne"},
            {"normaliserat_ord":"akne","homonr":"0","ordkl":"s. <i>+n</i>","urspr_lopnr":10,"subnr":10,"text":"+n","upos":"NOUN","ord":"acne"},
            {"normaliserat_ord":"akne","homonr":"1","ordkl":"(hv)","urspr_lopnr":20,"subnr":20,"text":"(null)","upos":"X","ord":"acne"},
        ]
        articles, headings, references, summary = materialize(rows)
        self.assertEqual(1, len(articles))
        self.assertEqual("10:10:1", articles[0]["article_id"])
        self.assertEqual({("akne", "primary"), ("acne", "alternate")}, {(r["heading"], r["heading_type"]) for r in headings})
        self.assertEqual(1, len(references))
        self.assertEqual("acne", references[0]["source_heading"])
        self.assertEqual("akne", references[0]["target_lemma"])
        self.assertEqual("plain_reference", references[0]["reference_type"])
        self.assertEqual(0, summary["dangling_headings"])
        self.assertEqual(0, summary["raw_rows_minus_accounted"])

    def test_keeps_real_homonyms_separate_and_classifies_inflection_reference(self) -> None:
        rows = [
            {"normaliserat_ord":"få","homonr":"1","ordkl":"v.","urspr_lopnr":30,"subnr":30,"text":"fick","upos":"VERB","ord":"<sup>1</sup>få"},
            {"normaliserat_ord":"få","homonr":"2","ordkl":"adj.","urspr_lopnr":31,"subnr":31,"text":"komp. färre","upos":"ADJ","ord":"<sup>2</sup>få"},
            {"normaliserat_ord":"få","homonr":"0","ordkl":"(hv) <i>komp.</i>","urspr_lopnr":40,"subnr":40,"text":"komp.","upos":"X","ord":"färre"},
        ]
        articles, headings, references, summary = materialize(rows)
        self.assertEqual({"30:30:1", "31:31:2"}, {row["article_id"] for row in articles})
        self.assertEqual(2, len(headings))
        self.assertEqual("inflection_reference", references[0]["reference_type"])
        self.assertEqual(0, summary["unresolved"])
        self.assertEqual(0, summary["raw_rows_minus_accounted"])


if __name__ == "__main__":
    unittest.main()
