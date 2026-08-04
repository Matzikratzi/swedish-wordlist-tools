from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from swedish_wordlist_tools.analyze_verb_compound_heads import build_report


class AnalyzeVerbCompoundHeadsTests(unittest.TestCase):
    def record(self, lemma: str, text: str, stycke: str) -> dict[str, object]:
        return {
            "normaliserat_ord": lemma,
            "text": text,
            "stycke": stycke,
            "upos": "VERB",
            "ordkl": "v.",
        }

    def write_records(self, records: list[dict[str, object]]) -> Path:
        handle = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".jsonl",
            delete=False,
        )
        with handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        self.addCleanup(Path(handle.name).unlink, missing_ok=True)
        return Path(handle.name)

    def test_reports_repairs_for_all_core_verb_slots(self) -> None:
        base = self.record("skriva", "(null)", "skriva")
        family = self.record(
            "renskriva",
            "-skrev, -skrivit, pres. -skriver",
            "ren|skriva",
        )
        # Preterite and supine are parsed as strict prefixes and repaired.
        # The final present token reaches the 50-character hard cap, so the
        # parser drops it and compound-head recovery adds the missing slot.
        target_text = "-skr, -skriv, pres. -skr".ljust(50)
        self.assertEqual(50, len(target_text))
        target = self.record("avskriva", target_text, "av|skriva")

        report = build_report(self.write_records([base, family, target]))

        self.assertEqual(1, report["partly_enriched_rows"])
        self.assertEqual({"present": 1}, report["borrowed_slot_counts"])
        self.assertEqual(
            {"preterite": 1, "supine": 1},
            report["repaired_slot_counts"],
        )
        example = report["examples"][0]
        self.assertEqual(["present"], example["added_slots"])
        self.assertEqual(
            ["preterite", "supine"],
            sorted(example["repaired_slots"]),
        )
        self.assertEqual(["avskriver"], example["forms_after"]["present"])
        self.assertEqual(["avskrev"], example["forms_after"]["preterite"])
        self.assertEqual(["avskrivit"], example["forms_after"]["supine"])

    def test_missing_slots_are_reported_separately_from_repairs(self) -> None:
        base = self.record("ge", "gav, gett, pres. ger", "ge")
        target_text = "-gav, -gett, deltagande deltagandet deltaganden".ljust(50)
        self.assertEqual(50, len(target_text))
        target = self.record("ange", target_text, "an|ge")

        report = build_report(self.write_records([base, target]))

        self.assertEqual({"present": 1}, report["borrowed_slot_counts"])
        self.assertEqual({}, report["repaired_slot_counts"])
        example = report["examples"][0]
        self.assertEqual(["present"], example["added_slots"])
        self.assertEqual([], example["repaired_slots"])
        self.assertEqual(["anger"], example["forms_after"]["present"])


if __name__ == "__main__":
    unittest.main()
