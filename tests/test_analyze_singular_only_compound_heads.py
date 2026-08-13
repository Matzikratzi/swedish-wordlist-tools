import unittest

from swedish_wordlist_tools.analyze_singular_only_compound_heads import analyze


class SingularOnlyCompoundHeadsTests(unittest.TestCase):
    def test_finds_compound_whose_head_has_explicit_plural(self):
        rows = [
            {
                "upos": "NOUN",
                "normaliserat_ord": "fostbrödraskap",
                "homonr": "1",
                "text": "+et",
                "stycke": "fost|brödra·skap",
            },
            {
                "upos": "NOUN",
                "normaliserat_ord": "brödraskap",
                "homonr": "1",
                "text": "+et +",
                "stycke": "brödra·skap",
            },
        ]
        result = analyze(rows)
        self.assertEqual(1, len(result))
        self.assertEqual("fostbrödraskap", result[0]["lemma"])
        self.assertEqual("brödraskap", result[0]["head"])

    def test_ignores_compound_when_head_also_has_no_plural(self):
        rows = [
            {
                "upos": "NOUN",
                "normaliserat_ord": "kyrkofrid",
                "homonr": "1",
                "text": "+en",
                "stycke": "kyrko|frid",
            },
            {
                "upos": "NOUN",
                "normaliserat_ord": "frid",
                "homonr": "1",
                "text": "+en",
                "stycke": "frid",
            },
        ]
        self.assertEqual([], analyze(rows))


if __name__ == "__main__":
    unittest.main()
