import unittest

from swedish_wordlist_tools.msd import Msd, parse_msd


class MsdTests(unittest.TestCase):
    def test_parses_plain_grammar(self) -> None:
        msd = parse_msd("sg def nom")

        self.assertEqual(msd.raw, "sg def nom")
        self.assertEqual(msd.tags, ("sg", "def", "nom"))
        self.assertIsNone(msd.paradigm)
        self.assertFalse(msd.has_paradigm)
        self.assertEqual(msd.grammar, "sg def nom")

    def test_separates_paradigm_position(self) -> None:
        msd = parse_msd("pres ind aktiv 1:2-2")

        self.assertEqual(msd.tags, ("pres", "ind", "aktiv"))
        self.assertEqual(msd.paradigm, "1:2-2")
        self.assertTrue(msd.has_paradigm)
        self.assertEqual(msd.grammar, "pres ind aktiv")

    def test_round_trip_preserves_raw_value(self) -> None:
        for raw in (
            "ci",
            "sg def gen",
            "pret_part indef sg n nom 2:1-1",
            "",
            "  sg   def nom  ",
        ):
            with self.subTest(raw=raw):
                self.assertEqual(str(parse_msd(raw)), raw)

    def test_parse_accepts_existing_instance(self) -> None:
        original = Msd.parse("inf aktiv 1:1-2")
        self.assertIs(parse_msd(original), original)

    def test_rejects_non_string_values(self) -> None:
        with self.assertRaises(TypeError):
            parse_msd(123)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
