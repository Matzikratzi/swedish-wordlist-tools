from __future__ import annotations
import json,tempfile,unittest
from pathlib import Path
from swedish_wordlist_tools.ocr_compare_baseline import compare
class CompareBaselineTest(unittest.TestCase):
 def _write(self,path,rows):Path(path).write_text("".join(json.dumps(r)+"\n" for r in rows),encoding="utf-8")
 def _row(self):return {"page":1,"column":0,"row":0,"baseline":12,"text":"abc","matches":[],"covered_pixels":3,"source_pixels":3,"fully_exact":True,"needs_work":False,"unreviewed_matches":0,"crop_box":[0,0,3,4]}
 def test_identical_stable_result_has_no_difference(self):
  row=self._row()
  with tempfile.TemporaryDirectory() as td:
   a,b=Path(td)/"a.jsonl",Path(td)/"b.jsonl";self._write(a,[row]);self._write(b,[{**row,"elapsed":99.0}]);self.assertEqual(compare(a,b),[])
 def test_changed_ocr_result_is_reported(self):
  row=self._row()
  with tempfile.TemporaryDirectory() as td:
   a,b=Path(td)/"a.jsonl",Path(td)/"b.jsonl";self._write(a,[row]);self._write(b,[{**row,"baseline":13}]);self.assertEqual(compare(a,b)[0]["kind"],"changed")
if __name__=="__main__":unittest.main()
