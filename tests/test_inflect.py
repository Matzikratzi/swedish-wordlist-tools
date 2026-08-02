from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from swedish_wordlist_tools.inflect import (
    COMMON_PATTERNS,
    EXPLICIT_PATTERN_GROUP,
    GeneratedWordForm,
    build_wordlist,
    generate_entry,
    generate_forms,
    normalise_pattern,
)
from swedish_wordlist_tools.msd import Msd


class InflectTests(unittest.TestCase):
    def test_generates_common_noun_forms(self) -> None:
        self.assertEqual(generate_forms("abakus", "+en +er"), ("abakus", "abakusen", "abakuser"))
        self.assertEqual(generate_forms("abbé", "+n +er"), ("abbé", "abbén", "abbéer"))

    def test_strips_bracketed_pronunciation_annotations(self) -> None:
        self.assertEqual("+n +er", normalise_pattern("+n +er [-o>r-]"))
        self.assertEqual("+n +r", normalise_pattern("+n [-en]; pl. +r [-er]"))
        self.assertEqual("+t", normalise_pattern("+t [-et]"))
        self.assertEqual("+en +er", normalise_pattern("+en [bordå>n]; pl. +er"))

    def test_generates_key_forms_from_bracketed_pronunciation_annotations(self) -> None:
        self.assertEqual(
            ("reaktor", "reaktorn", "reaktorer"),
            generate_forms("reaktor", "+n +er [-o>r-]"),
        )
        self.assertEqual(
            ("baguette", "baguetten", "baguetter"),
            generate_forms("baguette", "+n [-en]; pl. +r [-er]"),
        )

    def test_generates_adjective_and_verb_forms(self) -> None:
        self.assertEqual(generate_forms("abchazisk", "+t +a"), ("abchazisk", "abchaziskt", "abchaziska"))
        self.assertEqual(generate_forms("abonnera", "+de +t"), ("abonnera", "abonnerade", "abonnerat"))

    def test_inflects_verb_before_reflexive_pronoun(self) -> None:
        self.assertEqual(
            generate_forms("blamera sig", "+de +t"),
            ("blamera sig", "blamerade sig", "blamerat sig"),
        )

    def test_uses_complete_replacement_forms(self) -> None:
        self.assertEqual(generate_forms("klocka", "+n klockor"), ("klocka", "klockan", "klockor"))
        self.assertEqual(generate_forms("gå", "går gick gått"), ("gå", "går", "gick", "gått"))
        entry = generate_entry({"normaliserat_ord": "klocka", "text": "+n klockor"})
        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry.pattern_group, EXPLICIT_PATTERN_GROUP)

    def test_supports_alternative_suffixes(self) -> None:
        self.assertEqual(
            generate_forms("bikarbonat", "+en el. +et; pl. +er"),
            ("bikarbonat", "bikarbonaten", "bikarbonatet", "bikarbonater"),
        )
        entry = generate_entry({
            "normaliserat_ord": "bikarbonat",
            "text": "+en el. +et; pl. +er",
        })
        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry.form_kinds, ("lemma", "derived", "derived", "plural"))

    def test_replaces_final_compound_component(self) -> None:
        self.assertEqual(
            generate_forms("bagagekärra", "+n -kärror"),
            ("bagagekärra", "bagagekärran", "bagagekärror"),
        )
        self.assertEqual(
            generate_forms("damcykel", "+n -cyklar"),
            ("damcykel", "damcykeln", "damcyklar"),
        )
        self.assertEqual(
            generate_forms("sondotter", "+n -döttrar"),
            ("sondotter", "sondottern", "sondöttrar"),
        )
        self.assertEqual(
            generate_forms("utskriva", "-skrev -skrivit"),
            ("utskriva", "utskrev", "utskrivit"),
        )

    def test_tracks_definite_plural_separately(self) -> None:
        entry = generate_entry({
            "normaliserat_ord": "dyrkare",
            "text": "+n; pl. +, best. pl. dyrkarna",
        })
        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry.forms, ("dyrkare", "dyrkaren", "dyrkarna"))
        self.assertEqual(entry.form_kinds, ("lemma", "derived", "definite_plural"))

        compound = generate_entry({
            "normaliserat_ord": "förlossningsläkare",
            "text": "+n; pl. +, best. pl. -läkarna",
        })
        self.assertIsNotNone(compound)
        assert compound is not None
        self.assertEqual(
            compound.forms,
            ("förlossningsläkare", "förlossningsläkaren", "förlossningsläkarna"),
        )
        self.assertEqual(compound.form_kinds[-1], "definite_plural")

    def test_plural_plus_does_not_duplicate_exported_spelling(self) -> None:
        self.assertEqual(generate_forms("A-avdrag", "+et; pl. +"), ("A-avdrag", "A-avdraget"))
        entry = generate_entry({
            "normaliserat_ord": "A-avdrag",
            "text": "+et; pl. +",
            "upos": "NOUN",
        })
        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(
            [(form.written_form, str(form.msd)) for form in entry.word_forms],
            [
                ("A-avdrag", "ci"),
                ("A-avdraget", "sg def nom"),
                ("A-avdrag", "pl indef nom"),
            ],
        )

    def test_rejects_missing_and_malformed_patterns(self) -> None:
        self.assertIsNone(generate_forms("gå", None))
        self.assertIsNone(generate_forms("gå", "???"))
        self.assertIsNone(generate_forms("", "+en"))
        self.assertIsNone(normalise_pattern("(null)"))

    def test_all_initial_patterns_are_registered(self) -> None:
        self.assertEqual(len(COMMON_PATTERNS), 11)

    def test_generates_typed_noun_word_forms(self) -> None:
        entry = generate_entry({"normaliserat_ord": "aktie", "text": "+n +r", "upos": "NOUN"})
        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry.forms, ("aktie", "aktien", "aktier"))
        self.assertTrue(all(isinstance(form, GeneratedWordForm) for form in entry.word_forms))
        self.assertTrue(all(isinstance(form.msd, Msd) for form in entry.word_forms))
        self.assertEqual(
            [str(form.msd) for form in entry.word_forms],
            ["ci", "sg def nom", "pl indef nom"],
        )

    def test_generates_typed_verb_word_forms(self) -> None:
        entry = generate_entry({"normaliserat_ord": "abonnera", "text": "+de +t", "upos": "VERB"})
        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(
            [(form.written_form, str(form.msd)) for form in entry.word_forms],
            [
                ("abonnera", "ci"),
                ("abonnerade", "pret ind aktiv"),
                ("abonnerat", "sup aktiv"),
            ],
        )

    def test_does_not_invent_ambiguous_adjective_msd(self) -> None:
        entry = generate_entry({"normaliserat_ord": "abchazisk", "text": "+t +a", "upos": "ADJ"})
        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(str(entry.word_forms[0].msd), "ci")
        self.assertEqual(str(entry.word_forms[1].msd), "pos indef sg n nom")
        self.assertIsNone(entry.word_forms[2].msd)

    def test_builds_deduplicated_wordlist_and_report(self) -> None:
        fixture = Path(__file__).parent / "fixtures" / "sample.jsonl"
        with TemporaryDirectory() as directory:
            output = Path(directory) / "forms.txt"
            report = build_wordlist(fixture, output)
            forms = output.read_text(encoding="utf-8").splitlines()
        self.assertEqual(report["source_records"], 4)
        self.assertEqual(report["supported_records"], 3)
        self.assertEqual(report["coverage_percent"], 75.0)
        self.assertIn("abakusen", forms)
        self.assertIn("A-avdraget", forms)
        self.assertIn("abbedissor", forms)
        self.assertIn("form_kind_counts", report)
        self.assertIn("typed_msd_counts", report)
        self.assertIn("untyped_word_forms", report)
        self.assertNotIn("a", forms)


if __name__ == "__main__":
    unittest.main()
