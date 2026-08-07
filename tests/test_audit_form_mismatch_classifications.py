from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from swedish_wordlist_tools.audit_form_mismatch_classifications import (
    NOT_APPLICABLE,
    STALE_VALIDATION,
    VERIFIED,
    audit_row,
    resolve_gamewords_path,
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
            "extra_from_saol": [
                "abstinenser",
                "abstinensers",
                "abstinenserna",
                "abstinensernas",
            ],
        }
        row.update(overrides)
        return row

    def test_verifies_artifact_backed_classification_present_in_gamewords(self):
        gamewords = {
            "abstinenser",
            "abstinensers",
            "abstinenserna",
            "abstinensernas",
        }
        audited = audit_row(self.row(), gamewords)
        self.assertEqual(VERIFIED, audited["classification_audit"])
        self.assertEqual([], audited["forms_missing_from_gamewords"])

    def test_rejects_old_record_local_noun_classification(self):
        audited = audit_row(
            self.row(generator="record_local_canonical"),
            {
                "abstinenser",
                "abstinensers",
                "abstinenserna",
                "abstinensernas",
            },
        )
        self.assertEqual(STALE_VALIDATION, audited["classification_audit"])
        self.assertIn(
            "non_artifact_generator:record_local_canonical",
            audited["classification_audit_reasons"],
        )

    def test_rejects_claimed_saol_form_absent_from_gamewords(self):
        audited = audit_row(
            self.row(
                lemma="apanage",
                notation="+t [-et]; pl. +",
                mismatch_classification="saldo_missing_definite_plural",
                extra_from_saol=["apanageen", "apanageens"],
            ),
            {"apanage", "apanages", "apanaget", "apanagets", "apanagen", "apanagens"},
        )
        self.assertEqual(STALE_VALIDATION, audited["classification_audit"])
        self.assertEqual(
            ["apanageen", "apanageens"],
            audited["forms_missing_from_gamewords"],
        )

    def test_unclassified_rows_are_not_applicable(self):
        audited = audit_row(
            self.row(mismatch_classification="unclassified"),
            set(),
        )
        self.assertEqual(NOT_APPLICABLE, audited["classification_audit"])

    def test_finds_unique_gamewords_file_recursively(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            expected = root / "nested" / "exports" / "saol14-gamewords.txt"
            expected.parent.mkdir(parents=True)
            expected.write_text("apanage\n", encoding="utf-8")
            self.assertEqual(expected, resolve_gamewords_path(root=root))

    def test_missing_gamewords_file_has_actionable_error(self):
        with tempfile.TemporaryDirectory() as tempdir:
            with self.assertRaisesRegex(FileNotFoundError, "find .*saol14-gamewords"):
                resolve_gamewords_path(root=Path(tempdir))


if __name__ == "__main__":
    unittest.main()
