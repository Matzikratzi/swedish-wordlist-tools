from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from swedish_wordlist_tools import ocr_capture_conservative_baseline as capture


class CaptureConservativeBaselineTest(unittest.TestCase):
    def test_row_record_contains_stable_comparison_fields(self):
        match=SimpleNamespace(label="a",style="roman",x=10,baseline=7,pixels={(10,7),(11,7)},sources=2)
        work=SimpleNamespace(covered_pixels=2,source_pixels=2,fully_exact=True,needs_work=False,unreviewed_matches=0)
        state={"crop_box":(1,2,20,12),"baseline":7,"text":"a","matches":[match]}
        with patch.object(capture.scanner,"classify_row_state",side_effect=AssertionError("must use supplied classification")):
            row=capture._row_record(3,(1,4),state,work)
        self.assertEqual((row["page"],row["column"],row["row"]),(3,1,4)); self.assertEqual(row["crop_box"],[1,2,20,12]); self.assertEqual(row["baseline"],7); self.assertEqual(row["text"],"a"); self.assertTrue(row["fully_exact"]); self.assertEqual(len(row["matches"]),1); self.assertEqual(row["matches"][0]["label"],"a"); self.assertEqual(len(row["matches"][0]["raster_sha256"]),64)


if __name__=="__main__": unittest.main()
