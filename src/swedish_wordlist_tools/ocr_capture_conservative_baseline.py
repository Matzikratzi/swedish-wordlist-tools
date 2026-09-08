from __future__ import annotations

"""Capture a reproducible baseline from the conservative SAOL14 OCR scanner."""

import argparse, hashlib, json, subprocess, sys
from pathlib import Path
from . import ocr_find_unreviewed_glyph_rows as scanner
from . import ocr_find_unreviewed_glyph_rows_conservative as conservative
from .ocr_glyph_facit_store import load_split_facit, verify_facit
FORMAT="saol14-ocr-conservative-baseline-v1"
def _sha256_file(path):
 d=hashlib.sha256()
 with Path(path).open("rb") as f:
  for c in iter(lambda:f.read(1024*1024),b""): d.update(c)
 return d.hexdigest()
def _sha256_tree(path):
 d=hashlib.sha256(); path=Path(path)
 for p in sorted(x for x in path.rglob("*") if x.is_file()): d.update(p.relative_to(path).as_posix().encode()); d.update(b"\0"); d.update(_sha256_file(p).encode()); d.update(b"\n")
 return d.hexdigest()
def _git_commit():
 try:return subprocess.check_output(["git","rev-parse","HEAD"],text=True,stderr=subprocess.DEVNULL).strip()
 except (OSError,subprocess.CalledProcessError):return None
def _match_record(m):
 pixels=tuple(sorted((int(x)-int(m.x),int(y)-int(m.baseline)) for x,y in m.pixels)); raster=json.dumps(pixels,separators=(",",":")).encode(); return {"label":str(m.label),"style":str(m.style),"x":int(m.x),"baseline":int(m.baseline),"model_pixels":len(pixels),"raster_sha256":hashlib.sha256(raster).hexdigest(),"sources":int(getattr(m,"sources",0) or 0)}
def _row_record(page,position,state,work=None):
 work=work if work is not None else scanner.classify_row_state(page,position,state); matches=list(state.get("matches") or []); matches.sort(key=lambda m:(int(m.x),int(m.baseline),str(m.label),str(m.style))); return {"page":int(page),"column":int(position[0]),"row":int(position[1]),"crop_box":[int(v) for v in state.get("crop_box") or ()],"baseline":None if state.get("baseline") is None else int(state["baseline"]),"covered_pixels":work.covered_pixels,"source_pixels":work.source_pixels,"fully_exact":work.fully_exact,"needs_work":work.needs_work,"unreviewed_matches":work.unreviewed_matches,"text":str(state.get("text") or ""),"matches":[_match_record(m) for m in matches]}
def main():
 ap=argparse.ArgumentParser(); ap.add_argument("jsonl",type=Path); ap.add_argument("--facit",type=Path,required=True); ap.add_argument("--start-page",type=int,required=True); ap.add_argument("--end-page",type=int,required=True); ap.add_argument("--threshold",type=int,default=210); ap.add_argument("--expect-facit-models",type=int); ap.add_argument("--output-dir",type=Path,required=True); a=ap.parse_args(); split=a.facit.parent/"facit-v2"; verify_facit(a.facit,split); payload=load_split_facit(split); n=len(payload.get("models") or [])
 if a.expect_facit_models is not None and n!=a.expect_facit_models: raise ValueError(f"expected {a.expect_facit_models} facit models, got {n}")
 out=a.output_dir; out.mkdir(parents=True,exist_ok=True); rp,pp,sp=out/"rows.jsonl",out/"problems.json",out/"summary.json"; fh=rp.open("w",encoding="utf-8"); rows=[]; problems=[]; old_classify=scanner.classify_row_state
 def capture(page,pos,state):
  work=old_classify(page,pos,state); rec=_row_record(page,pos,state,work); fh.write(json.dumps(rec,ensure_ascii=False,sort_keys=True)+"\n"); rows.append(rec); problems.append(rec) if work.needs_work else None; return work
 scanner.classify_row_state=capture; old_argv=sys.argv; sys.argv=[old_argv[0],str(a.jsonl),"--facit",str(a.facit),"--start-page",str(a.start_page),"--end-page",str(a.end_page),"--threshold",str(a.threshold)]
 try: result=conservative.main()
 finally: scanner.classify_row_state=old_classify; sys.argv=old_argv; fh.close()
 summary={"format":"saol14-ocr-baseline-summary-v1","pages":a.end_page-a.start_page+1,"rows":len(rows),"exact":sum(bool(r["fully_exact"]) for r in rows),"needs_work":len(problems),"facit_models":n}; sp.write_text(json.dumps(summary,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8"); pp.write_text(json.dumps({"format":"saol14-ocr-baseline-problems-v1","rows":problems},ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8"); manifest={"format":FORMAT,"algorithm":"ocr_find_unreviewed_glyph_rows_conservative","git_commit":_git_commit(),"parameters":{"start_page":a.start_page,"end_page":a.end_page,"threshold":a.threshold},"source":{"jsonl":str(a.jsonl),"sha256":_sha256_file(a.jsonl)},"facit":{"aggregate":str(a.facit),"aggregate_sha256":_sha256_file(a.facit),"split_store":str(split),"split_store_sha256":_sha256_tree(split),"models":n,"verified_equal":True},"outputs":{name:{"path":p.name,"sha256":_sha256_file(p)} for name,p in (("rows",rp),("problems",pp),("summary",sp))}}; (out/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8"); print(f"baseline: pages={summary['pages']} rows={summary['rows']} exact={summary['exact']}/{summary['rows']} needs_work={summary['needs_work']} facit_models={n}"); print(f"baseline: saved to {out}"); return result
if __name__=="__main__":raise SystemExit(main())
