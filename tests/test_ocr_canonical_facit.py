from __future__ import annotations
import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from swedish_wordlist_tools import ocr_canonical_facit as canonical
class CanonicalFacitTest(unittest.TestCase):
 def test_canonical_aggregate_loads_payload_from_split_store(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);aggregate=root/"saol14-manual-glyph-facit-v2.json";store=root/"facit-v2";store.mkdir();payload={"format":"saol14-manual-glyph-facit-v2","models":[{"id":"g000001"}]};aggregate.write_text("STALE",encoding="utf-8");seen={}
   def parse(path):seen["text"]=Path(path).read_text(encoding="utf-8");return ["parsed"]
   with patch.object(canonical,"load_split_facit",return_value=payload) as split,patch.object(canonical,"load_facit_with_typography",side_effect=parse):self.assertEqual(canonical.load_canonical_facit_with_typography(aggregate),["parsed"])
   split.assert_called_once_with(store);self.assertIn("g000001",seen["text"]);self.assertNotIn("STALE",seen["text"])
 def test_explicit_noncanonical_json_keeps_legacy_loader(self):
  with tempfile.TemporaryDirectory() as td:
   fixture=Path(td)/"frozen-facit.json"
   with patch.object(canonical,"load_facit_with_typography",return_value=["legacy"]) as parser:self.assertEqual(canonical.load_canonical_facit_with_typography(fixture),["legacy"])
   parser.assert_called_once_with(fixture)
if __name__=="__main__":unittest.main()
