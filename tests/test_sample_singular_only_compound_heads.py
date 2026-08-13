import unittest

from swedish_wordlist_tools.sample_singular_only_compound_heads import sample


class SingularOnlyCompoundHeadSampleTests(unittest.TestCase):
    def test_samples_only_target_family_and_respects_limit(self):
        rows = [
            {
                "upos": "NOUN",
                "normaliserat_ord": "hyperaktivitet",
                "homonr": "1",
                "text": "+en",
                "stycke": "hyper|akt·iv·itet",
            },
            {
                "upos": "NOUN",
                "normaliserat_ord": "radioaktivitet",
                "homonr": "1",
                "text": "+en",
                "stycke": "radio|akt·iv·itet",
            },
            {
                "upos": "NOUN",
                "normaliserat_ord": "överaktivitet",
                "homonr": "1",
                "text": "+en",
                "stycke": "över|akt·iv·itet",
            },
            {
                "upos": "NOUN",
                "normaliserat_ord": "aktivitet",
                "homonr": "1",
                "text": "+en +er",
                "stycke": "akt·iv·itet",
            },
            {
                "upos": "NOUN",
                "normaliserat_ord": "någotannat",
                "homonr": "1",
                "text": "+en",
                "stycke": "något|annat",
            },
            {
                "upos": "NOUN",
                "normaliserat_ord": "annat",
                "homonr": "1",
                "text": "+en +er",
                "stycke": "annat",
            },
        ]
        result = sample(rows, per_head=2)
        self.assertEqual(["hyperaktivitet", "radioaktivitet"], [row["lemma"] for row in result])

    def test_includes_fostbrodraskap_family(self):
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
        result = sample(rows)
        self.assertEqual(1, len(result))
        self.assertEqual("fostbrödraskap", result[0]["lemma"])


if __name__ == "__main__":
    unittest.main()
