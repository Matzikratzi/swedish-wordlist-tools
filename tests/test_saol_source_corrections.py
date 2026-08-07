from __future__ import annotations

import unittest

from swedish_wordlist_tools.saol_source_corrections import (
    apply_saol_source_corrections,
    interpret_corrected_adjective_slots,
    source_correction_rows,
)


class SaolSourceCorrectionsTests(unittest.TestCase):
    def test_anhorig_sign_error_is_corrected_exactly(self) -> None:
        record = {
            "normaliserat_ord": "anhörig",
            "homonr": "1",
            "text": "pl. -a",
            "stycke": "an|hör·ig",
            "upos": "ADJ",
        }
        corrected = apply_saol_source_corrections(record)
        self.assertEqual("pl. +a", corrected["text"])
        self.assertEqual("pl. -a", record["text"])

        slots = interpret_corrected_adjective_slots(record)
        self.assertIsNotNone(slots)
        assert slots is not None
        self.assertEqual(("anhörig", "anhöriga"), slots.written_forms())

    def test_correction_is_narrowly_scoped(self) -> None:
        record = {
            "normaliserat_ord": "anhörig",
            "homonr": "2",
            "text": "pl. -a",
            "stycke": "an|hör·ig",
            "upos": "ADJ",
        }
        self.assertIs(record, apply_saol_source_corrections(record))

    def test_report_keeps_evidence(self) -> None:
        rows = source_correction_rows()
        self.assertEqual(1, len(rows))
        self.assertEqual("anhörig", rows[0]["lemma"])
        self.assertIn("https://runeberg.org/saol/11-6/0013.html", rows[0]["evidence"])


if __name__ == "__main__":
    unittest.main()
