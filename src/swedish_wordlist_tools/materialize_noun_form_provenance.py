from __future__ import annotations

import argparse
import json
import os
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .canonical_form_artifacts import DEFAULT_NOUN_FORMS
from .jsonl import read_jsonl
from .noun_form_provenance import enrich_rows, written_form_signature

DEFAULT_AUDIT = Path("reports/saol14-noun-form-provenance-audit.txt")
DEFAULT_SUMMARY = Path("reports/saol14-noun-form-provenance-summary.json")


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def materialize(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    before = written_form_signature(rows)
    enriched = enrich_rows(rows)
    after = written_form_signature(enriched)
    source_counts: Counter[str] = Counter()
    generated_from_records = 0
    forms = 0
    multi_source_forms = 0

    for row in enriched:
        for form in row.get("forms", []):
            if not isinstance(form, dict):
                continue
            forms += 1
            sources = form.get("generated_from") or []
            generated_from_records += len(sources)
            if len(sources) > 1:
                multi_source_forms += 1
            for source in sources:
                if isinstance(source, dict):
                    source_counts[str(source.get("heading_type") or "unknown")] += 1

    summary = {
        "artifact_rows": len(rows),
        "forms": forms,
        "generated_from_records": generated_from_records,
        "multi_source_forms": multi_source_forms,
        "heading_type_counts": dict(sorted(source_counts.items())),
        "written_form_signature_unchanged": before == after,
    }
    return enriched, summary


def render(summary: dict[str, Any], path: Path) -> str:
    lines = [
        "SAOL14 noun form provenance",
        "",
        f"Artefakt: {path}",
        f"Artefaktrader: {summary['artifact_rows']}",
        f"Former: {summary['forms']}",
        f"generated_from-poster: {summary['generated_from_records']}",
        f"Former med flera källrubriker: {summary['multi_source_forms']}",
        f"Rubriktyper: {summary['heading_type_counts']}",
        f"Ordformsmängd oförändrad: {'JA' if summary['written_form_signature_unchanged'] else 'NEJ'}",
    ]
    return "\n".join(lines) + "\n"


def _replace_atomically(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        _write_jsonl(tmp, rows)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Add canonical generated_from provenance to the materialized SAOL noun-form artifact"
    )
    parser.add_argument("--noun-forms", type=Path, default=DEFAULT_NOUN_FORMS)
    parser.add_argument("--output", type=Path, default=None, help="default: rewrite --noun-forms atomically")
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    args = parser.parse_args()

    rows = list(read_jsonl(args.noun_forms))
    enriched, summary = materialize(rows)
    if not summary["written_form_signature_unchanged"]:
        raise SystemExit("Proveniensmaterialisering ändrade ordformsmängden; filen skrevs INTE.")

    output = args.output or args.noun_forms
    if output == args.noun_forms:
        _replace_atomically(output, enriched)
    else:
        _write_jsonl(output, enriched)

    args.audit.parent.mkdir(parents=True, exist_ok=True)
    args.audit.write_text(render(summary, output), encoding="utf-8")
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Former: {summary['forms']}")
    print(f"generated_from-poster: {summary['generated_from_records']}")
    print(f"Former med flera källrubriker: {summary['multi_source_forms']}")
    print(f"Ordformsmängd oförändrad: {'JA' if summary['written_form_signature_unchanged'] else 'NEJ'}")
    print(f"Artefakt: {output}")
    print(f"Audit: {args.audit}")


if __name__ == "__main__":
    main()
