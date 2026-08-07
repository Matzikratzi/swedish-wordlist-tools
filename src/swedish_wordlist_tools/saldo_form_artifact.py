from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from .artifact_paths import SALDO_FORMS
from .compare_sources import _key, read_saldo

DEFAULT_SALDO_XML = Path("data/raw/saldom.xml")
DEFAULT_SALDO_FORMS = SALDO_FORMS


def _unique_analyses(grouped: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    seen: set[int] = set()
    result: list[dict[str, Any]] = []
    for analyses in grouped.values():
        for analysis in analyses:
            marker = id(analysis)
            if marker in seen:
                continue
            seen.add(marker)
            result.append(analysis)
    return result


def export_saldo_forms(
    saldo_xml: Path = DEFAULT_SALDO_XML,
    output: Path = DEFAULT_SALDO_FORMS,
) -> dict[str, Any]:
    grouped = read_saldo(saldo_xml)
    rows = [
        {
            "id": str(analysis.get("id") or ""),
            "upos": str(analysis.get("upos") or "").upper(),
            "lemmas": sorted({str(value) for value in analysis.get("lemmas", ()) if str(value)}, key=str.casefold),
            "forms": sorted({str(value) for value in analysis.get("forms", ()) if str(value)}, key=str.casefold),
        }
        for analysis in _unique_analyses(grouped)
    ]
    rows.sort(
        key=lambda row: (
            (row["lemmas"][0].casefold() if row["lemmas"] else ""),
            row["upos"],
            row["id"],
        )
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return {
        "source": str(saldo_xml),
        "artifact": str(output),
        "analyses": len(rows),
        "unique_forms": len({form for row in rows for form in row["forms"]}),
    }


def read_saldo_forms(path: Path = DEFAULT_SALDO_FORMS) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"Ogiltig JSON på rad {number} i {path}") from error
            analysis = {
                "id": str(row.get("id") or ""),
                "upos": str(row.get("upos") or "").upper(),
                "lemmas": set(str(value) for value in row.get("lemmas", ()) if str(value)),
                "forms": set(str(value) for value in row.get("forms", ()) if str(value)),
            }
            for lemma in analysis["lemmas"]:
                grouped[_key(lemma)].append(analysis)
    return dict(grouped)


def build_form_index(
    saldo: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen: set[tuple[str, int]] = set()
    for analyses in saldo.values():
        for analysis in analyses:
            identity = id(analysis)
            for form in analysis["forms"]:
                key = _key(str(form))
                marker = (key, identity)
                if marker in seen:
                    continue
                seen.add(marker)
                result[key].append(analysis)
    return dict(result)


def main() -> None:
    parser = argparse.ArgumentParser(description="Exportera SALDO till en kanonisk formartefakt")
    parser.add_argument("saldo", nargs="?", type=Path, default=DEFAULT_SALDO_XML)
    parser.add_argument("--output", type=Path, default=DEFAULT_SALDO_FORMS)
    args = parser.parse_args()
    summary = export_saldo_forms(args.saldo, args.output)
    print(f"SALDO-analyser: {summary['analyses']}")
    print(f"Unika former: {summary['unique_forms']}")
    print(f"Källa: {summary['source']}")
    print(f"Artefakt: {summary['artifact']}")


if __name__ == "__main__":
    main()
