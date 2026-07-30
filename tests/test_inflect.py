from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from swedish_wordlist_tools.inflect import (
    COMMON_PATTERNS,
    EXPLICIT_PATTERN_GROUP,
    build_wordlist,
    generate_entry,
    generate_forms,
    normalise_pattern,
)


class InflectTests(unittest.TestCase):
    def test_generates_common_noun_forms(self) -> None:
        self.assertEqual(generate_forms("abakus", "+en +er"), ("abakus", "abakusen", "abakuser"))
        self.assertEqual(generate_forms("abbé", "+n +er"), ("abbé", "abbén", "abbéer"))

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

    def test_plural_plus_does_not_duplicate_lemma(self) -> None:
        self.assertEqual(generate_forms("A-avdrag", "+et; pl. +"), ("A-avdrag", "A-avdraget"))

    def test_rejects_missing_and_malformed_patterns(self) -> None:
        self.assertIsNone(generate_forms("gå", None))
        self.assertIsNone(generate_forms("gå", "???"))
        self.assertIsNone(generate_forms("", "+en"))
        self.assertIsNone(normalise_pattern("(null)"))

    def test_all_initial_patterns_are_registered(self) -> None:
        self.assertEqual(len(COMMON_PATTERNS), 11)

    def test_generates_entry_from_real_saol14_fields(self) -> None:
        entry = generate_entry({"normaliserat_ord": "aktie", "text": "+n +r", "upos": "NOUN"})
        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry.forms, ("aktie", "aktien", "aktier"))

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
        self.assertNotIn("a", forms)


if __name__ == "__main__":
    unittest.main()
