import unittest

from swedish_wordlist_tools.analyze_saldo_forms_beyond_saol_scope import candidates


class SaldoFormsBeyondSaolScopeTests(unittest.TestCase):
    def test_finds_extra_forms_when_saol_only_has_definite_singular(self):
        rows = [{
            "upos": "NOUN",
            "lemma": "kyrkofrid",
            "homonym_number": "1",
            "record_id": "1",
            "notation": "+en",
            "generated_forms": ["kyrkofrid", "kyrkofrids", "kyrkofriden", "kyrkofridens"],
            "saldo_forms": [
                "kyrkofrid", "kyrkofrids", "kyrkofriden", "kyrkofridens",
                "kyrkofrider", "kyrkofriders", "kyrkofriderna", "kyrkofridernas",
            ],
        }]
        result = candidates(rows)
        self.assertEqual(1, len(result))
        self.assertEqual(
            ["+er", "+erna", "+ernas", "+ers"],
            result[0]["saldo_only_relative"],
        )

    def test_does_not_select_explicit_plural_notation(self):
        rows = [{
            "upos": "NOUN",
            "lemma": "allvarlighet",
            "notation": "+en +er",
            "generated_forms": ["allvarlighet", "allvarligheten", "allvarligheter"],
            "saldo_forms": ["allvarlighet", "allvarligheten", "allvarligheter", "allvarligheterna"],
        }]
        self.assertEqual([], candidates(rows))

    def test_does_not_select_when_saldo_has_no_extra_forms(self):
        rows = [{
            "upos": "NOUN",
            "lemma": "fostbrödraskap",
            "notation": "+et",
            "generated_forms": ["fostbrödraskap", "fostbrödraskaps", "fostbrödraskapet", "fostbrödraskapets"],
            "saldo_forms": ["fostbrödraskap", "fostbrödraskaps", "fostbrödraskapet", "fostbrödraskapets"],
        }]
        self.assertEqual([], candidates(rows))


if __name__ == "__main__":
    unittest.main()
