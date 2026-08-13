from __future__ import annotations

import unittest

from swedish_wordlist_tools.audit_form_mismatch_classifications import (
    NOT_APPLICABLE,
    STALE_VALIDATION,
    VERIFIED,
    audit_row,
)


class AuditFormMismatchClassificationsTests(unittest.TestCase):
    def row(self, **overrides):
        row = {
            "lemma": "abstinens",
            "homonym_number": "1",
            "upos": "NOUN",
            "notation": "+en +er",
            "generator": "canonical_artifact",
            "mismatch_classification": "saldo_missing_plural",
            "generated_forms": [
                "abstinens",
                "abstinenss",
                "abstinensen",
                "abstinensens",
                "abstinenser",
                "abstinensers",
                "abstinenserna",
                "abstinensernas",
            ],
            "extra_from_saol": [
                "abstinenser",
                "abstinensers",
                "abstinenserna",
                "abstinensernas",
            ],
        }
        row.update(overrides)
        return row

    def test_verifies_artifact_backed_classification_against_same_record(self):
        audited = audit_row(self.row())
        self.assertEqual(VERIFIED, audited["classification_audit"])
        self.assertEqual([], audited["forms_missing_from_canonical_record"])
        self.assertEqual([], audited["forms_missing_from_gamewords"])

    def test_rejects_old_record_local_noun_classification(self):
        audited = audit_row(self.row(generator="record_local_canonical"))
        self.assertEqual(STALE_VALIDATION, audited["classification_audit"])
        self.assertIn(
            "non_artifact_generator:record_local_canonical",
            audited["classification_audit_reasons"],
        )

    def test_rejects_claimed_saol_form_absent_from_canonical_record(self):
        audited = audit_row(
            self.row(
                lemma="apanage",
                notation="+t [-et]; pl. +",
                mismatch_classification="saldo_missing_definite_plural",
                generated_forms=[
                    "apanage",
                    "apanages",
                    "apanaget",
                    "apanagets",
                    "apanagen",
                    "apanagens",
                ],
                extra_from_saol=["apanageen", "apanageens"],
            )
        )
        self.assertEqual(STALE_VALIDATION, audited["classification_audit"])
        self.assertEqual(
            ["apanageen", "apanageens"],
            audited["forms_missing_from_canonical_record"],
        )

    def test_optional_gamewords_cross_check_can_reject_global_absence(self):
        audited = audit_row(
            self.row(),
            {"abstinenser", "abstinensers"},
        )
        self.assertEqual(STALE_VALIDATION, audited["classification_audit"])
        self.assertEqual(
            ["abstinenserna", "abstinensernas"],
            audited["forms_missing_from_gamewords"],
        )

    def test_unclassified_rows_are_not_applicable(self):
        audited = audit_row(
            self.row(mismatch_classification="unclassified"),
        )
        self.assertEqual(NOT_APPLICABLE, audited["classification_audit"])


if __name__ == "__main__":
    unittest.main()
