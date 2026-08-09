from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .canonical_form_artifacts import artifact_row_keys, read_artifact_rows

DEFAULT_VALIDATION = Path("reports/saol14-direct-form-validation.jsonl")
DEFAULT_NOUN_FORMS = Path("reports/saol14-noun-forms.jsonl")
DEFAULT_TEXT = Path("reports/saol14-remaining-noun-provenance.txt")
DEFAULT_JSON = Path("reports/saol14-remaining-noun-provenance.json")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _validation_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("record_id") or ""),
        str(row.get("homonym_number") or ""),
        str(row.get("lemma") or "").casefold(),
    )


def _artifact_form_kinds(rows: Iterable[dict[str, Any]]) -> dict[tuple[str, str, str], dict[str, set[str]]]:
    result: dict[tuple[str, str, str], dict[str, set[str]]] = {}
    for row in rows:
        kinds: dict[str, set[str]] = defaultdict(set)
        for form in row.get("forms", ()):
            written = str(form.get("written_form") or "")
            kind = str(form.get("kind") or "")
            if written:
                kinds[written.casefold()].add(kind)
        value = {form: set(values) for form, values in kinds.items()}
        for key in artifact_row_keys(row):
            result[key] = value
    return result


def _bucket(kinds: set[str]) -> str:
    direct = bool(kinds & {"lemma", "interpreted_slot"})
    derived = bool(kinds & {"derived_genitive", "derived_definite_plural"})
    if direct and derived:
        return "mixed_direct_and_derived"
    if derived:
        return "derived_only"
    if direct:
        return "direct_saol_slots_only"
    return "unmapped"


def analyze(
    validation_rows: Iterable[dict[str, Any]],
    artifact_rows: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    form_kinds = _artifact_form_kinds(artifact_rows)
    rows: list[dict[str, Any]] = []
    bucket_counts: Counter[str] = Counter()
    kind_counts: Counter[str] = Counter()
    notation_counts: dict[str, Counter[str]] = defaultdict(Counter)
    examples: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in validation_rows:
        if str(row.get("upos") or "").upper() != "NOUN":
            continue
        if str(row.get("status") or "") != "form_set_mismatch":
            continue

        extras = [str(value) for value in row.get("extra_from_saol", ()) if str(value)]
        artifact = form_kinds.get(_validation_key(row), {})
        extra_details: list[dict[str, Any]] = []
        aggregate_kinds: set[str] = set()
        for form in extras:
            kinds = set(artifact.get(form.casefold(), set()))
            aggregate_kinds.update(kinds)
            for kind in kinds:
                kind_counts[kind] += 1
            extra_details.append({"form": form, "kinds": sorted(kinds)})

        bucket = _bucket(aggregate_kinds)
        notation = str(row.get("notation") or "(null)")
        bucket_counts[bucket] += 1
        notation_counts[bucket][notation] += 1
        out = {
            "record_id": str(row.get("record_id") or ""),
            "homonym_number": str(row.get("homonym_number") or ""),
            "lemma": str(row.get("lemma") or ""),
            "notation": notation,
            "bucket": bucket,
            "extra_from_saol": extra_details,
            "missing_from_saol": list(row.get("missing_from_saol", ())),
        }
        rows.append(out)
        if len(examples[bucket]) < 20:
            examples[bucket].append(out)

    return {
        "records": len(rows),
        "bucket_counts": dict(bucket_counts.most_common()),
        "extra_form_kind_counts": dict(kind_counts.most_common()),
        "top_notations_by_bucket": {
            bucket: [{"notation": notation, "count": count} for notation, count in counter.most_common(30)]
            for bucket, counter in notation_counts.items()
        },
        "examples": dict(examples),
        "rows": rows,
    }


def render(summary: dict[str, Any]) -> str:
    lines = [
        "SAOL14 NOUN: provenance för kvarvarande form_set_mismatch",
        "",
        "Syfte: skilj mismatch som består av direkt SAOL-licensierade former från mismatch",
        "som innehåller former härledda av noun completion. SALDO används endast för att välja",
        "mismatchpopulationen; proveniensklassningen kommer från den kanoniska NOUN-artefakten.",
        "",
        f"Poster: {summary['records']}",
        "",
        "Hinkar:",
    ]
    for bucket, count in summary["bucket_counts"].items():
        lines.append(f"{count:6}  {bucket}")

    lines.extend(["", "Extra SAOL-former per generator-kind:"])
    for kind, count in summary["extra_form_kind_counts"].items():
        lines.append(f"{count:6}  {kind}")

    for bucket in ("derived_only", "mixed_direct_and_derived", "direct_saol_slots_only", "unmapped"):
        top = summary["top_notations_by_bucket"].get(bucket, [])
        if not top:
            continue
        lines.extend(["", f"Största notationer: {bucket}"])
        for item in top[:20]:
            lines.append(f"{item['count']:6}  {item['notation']}")
        examples = summary["examples"].get(bucket, [])
        if examples:
            lines.append("  Exempel:")
            for row in examples[:12]:
                extra = ", ".join(
                    f"{item['form']}[{'+'.join(item['kinds']) or '?'}]"
                    for item in row["extra_from_saol"]
                ) or "-"
                missing = ", ".join(row["missing_from_saol"]) or "-"
                lines.append(
                    f"    {row['lemma']} ({row['homonym_number']}) | {row['notation']} | "
                    f"SAOL-extra: {extra} | SALDO-extra: {missing}"
                )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validation", type=Path, default=DEFAULT_VALIDATION)
    parser.add_argument("--noun-forms", type=Path, default=DEFAULT_NOUN_FORMS)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()

    summary = analyze(_read_jsonl(args.validation), read_artifact_rows(args.noun_forms))
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render(summary), encoding="utf-8")
    args.json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Poster: {summary['records']}")
    for bucket, count in summary["bucket_counts"].items():
        print(f"{bucket}: {count}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
