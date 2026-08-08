import unittest

from swedish_wordlist_tools.analyze_saol_scope_families import build, family_for


class SaolScopeFamiliesTests(unittest.TestCase):
    def test_family_detection(self):
        self.assertEqual("-ering/-isering/-ifiering", family_for("acklimatisering"))
        self.assertEqual("-ism", family_for("absolutism"))
        self.assertEqual("-itet", family_for("aciditet"))
        self.assertEqual("-tion/-sion", family_for("absolution"))
        self.assertEqual("-skap", family_for("fostbrödraskap"))
        self.assertEqual("-ande/-ende", family_for("accepterande"))

    def test_build_groups_rows(self):
        rows = [
            {"lemma": "absolutism", "notation": "+en", "saldo_only_relative": ["+er"]},
            {"lemma": "aktivism", "notation": "+en", "saldo_only_relative": ["+er"]},
            {"lemma": "aciditet", "notation": "+en", "saldo_only_relative": ["+er"]},
        ]
        summary = build(rows)
        self.assertEqual(3, summary["records"])
        counts = {item["family"]: item["count"] for item in summary["families"]}
        self.assertEqual(2, counts["-ism"])
        self.assertEqual(1, counts["-itet"])


if __name__ == "__main__":
    unittest.main()
