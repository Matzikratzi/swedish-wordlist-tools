from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .saldo_form_artifact import DEFAULT_SALDO_FORMS, build_form_index, read_saldo_forms

DEFAULT_ALIGNMENT = Path("reports/saol14-noun-article-saldo-alignment.jsonl")
DEFAULT_TEXT = Path("reports/saol14-noun-missing-saldo-evidence.txt")
DEFAULT_JSONL = Path("reports/saol14-noun-missing-saldo-evidence.jsonl")
DEFAULT_SUMMARY = Path("reports/saol14-noun-missing-saldo-evidence-summary.json")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValueError(f"Ogiltig JSON på rad {number} i {path}") from error
    return rows


def _separator_key(value: str) -> str:
    return re.sub(r"[\s\-‐‑‒–—'’]+", "", value.casefold())


def _diacritic_key(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _loose_key(value: str) -> str:
    return re.sub(r"[^0-9a-z]+", "", _diacritic_key(value))


def _unique_analyses(saldo: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[int] = set()
    for analyses in saldo.values():
        for analysis in analyses:
            if str(analysis.get("upos") or "").upper() != "NOUN":
                continue
            marker = id(analysis)
            if marker in seen:
                continue
            seen.add(marker)
            result.append(analysis)
    return result


def _lemma_indexes(saldo: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, set[str]]]:
    indexes: dict[str, dict[str, set[str]]] = {
        "casefold": defaultdict(set),
        "separator": defaultdict(set),
        "diacritic": defaultdict(set),
        "loose": defaultdict(set),
    }
    for analysis in _unique_analyses(saldo):
        for lemma in analysis.get("lemmas", ()):
            text = str(lemma)
            indexes["casefold"][text.casefold()].add(text)
            indexes["separator"][_separator_key(text)].add(text)
            indexes["diacritic"][_diacritic_key(text)].add(text)
            indexes["loose"][_loose_key(text)].add(text)
    return indexes


def _orthographic_candidates(lemma: str, indexes: dict[str, dict[str, set[str]]]) -> tuple[str | None, list[str]]:
    folded = lemma.casefold()
    exact = sorted(indexes["casefold"].get(folded, ()), key=str.casefold)
    if exact:
        return "case_only", exact

    separator = sorted(indexes["separator"].get(_separator_key(lemma), ()), key=str.casefold)
    separator = [candidate for candidate in separator if candidate.casefold() != folded]
    if separator:
        return "separator_only", separator

    diacritic = sorted(indexes["diacritic"].get(_diacritic_key(lemma), ()), key=str.casefold)
    diacritic = [candidate for candidate in diacritic if candidate.casefold() != folded]
    if diacritic:
        return "diacritic_only", diacritic

    loose = sorted(indexes["loose"].get(_loose_key(lemma), ()), key=str.casefold)
    loose = [candidate for candidate in loose if candidate.casefold() != folded]
    if loose:
        return "loose_orthography", loose
    return None, []


def _analysis_lemmas(analysis: dict[str, Any]) -> set[str]:
    return {str(value) for value in analysis.get("lemmas", ()) if str(value)}


def _form_overlap_evidence(
    saol_forms: Iterable[str],
    form_index: dict[str, list[dict[str, Any]]],
) -> tuple[int, int, list[str]]:
    forms = {str(value) for value in saol_forms if str(value)}
    matched_forms: set[str] = set()
    candidate_counts: Counter[str] = Counter()
    for form in forms:
        analyses = [
            analysis for analysis in form_index.get(form.casefold(), ())
            if str(analysis.get("upos") or "").upper() == "NOUN"
        ]
        if not analyses:
            continue
        matched_forms.add(form)
        for analysis in analyses:
            for lemma in _analysis_lemmas(analysis):
                candidate_counts[lemma] += 1
    candidates = [lemma for lemma, _count in candidate_counts.most_common(12)]
    return len(matched_forms), len(forms), candidates


def classify_missing_variants(
    alignment_rows: Iterable[dict[str, Any]],
    saldo: dict[str, list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    indexes = _lemma_indexes(saldo)
    form_index = build_form_index(saldo)
    output: list[dict[str, Any]] = []

    for article in alignment_rows:
        for variant in article.get("variants", ()):
            if str(variant.get("status") or "") != "missing":
                continue
            lemma = str(variant.get("lemma") or "")
            saol_forms = [str(value) for value in variant.get("saol_forms", ()) if str(value)]
            orthographic_kind, orthographic_candidates = _orthographic_candidates(lemma, indexes)
            overlap_count, form_count, form_candidates = _form_overlap_evidence(saol_forms, form_index)
            overlap_ratio = (overlap_count / form_count) if form_count else 0.0

            if orthographic_candidates:
                classification = "orthographic_saldo_candidate"
            elif overlap_count >= 2 and overlap_ratio >= 0.5:
                classification = "strong_other_lemma_form_evidence"
            elif overlap_count:
                classification = "weak_or_ambiguous_form_evidence"
            else:
                classification = "no_saldo_evidence"

            output.append({
                "article_id": str(article.get("article_id") or article.get("record_id") or ""),
                "article_lemma": str(article.get("article_lemma") or ""),
                "variant_mode": str(article.get("variant_mode") or ""),
                "lemma": lemma,
                "classification": classification,
                "orthographic_kind": orthographic_kind,
                "orthographic_candidates": orthographic_candidates,
                "saol_forms": sorted(set(saol_forms), key=str.casefold),
                "saldo_form_overlap_count": overlap_count,
                "saol_form_count": form_count,
                "saldo_form_overlap_ratio": round(overlap_ratio, 4),
                "form_evidence_candidate_lemmas": form_candidates,
            })

    output.sort(key=lambda row: (row["classification"], row["lemma"].casefold(), row["article_id"]))
    classification_counts = Counter(row["classification"] for row in output)
    orthographic_counts = Counter(
        row["orthographic_kind"] for row in output if row["orthographic_kind"]
    )
    mode_counts = Counter(row["variant_mode"] for row in output)
    summary = {
        "missing_variants": len(output),
        "classification_counts": dict(sorted(classification_counts.items())),
        "orthographic_kind_counts": dict(sorted(orthographic_counts.items())),
        "variant_mode_counts": dict(sorted(mode_counts.items())),
    }
    return output, summary


def render(rows: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    lines = [
        f"Saknade variantparadigm: {summary['missing_variants']}",
        f"Klassningar: {summary['classification_counts']}",
        f"Ortografiska träfftyper: {summary['orthographic_kind_counts']}",
        f"Variantlägen: {summary['variant_mode_counts']}",
        "",
    ]
    headings = (
        ("orthographic_saldo_candidate", "Ortografiska SALDO-kandidater"),
        ("strong_other_lemma_form_evidence", "Stark formevidens under annat SALDO-lemma"),
        ("weak_or_ambiguous_form_evidence", "Svag eller tvetydig formevidens"),
        ("no_saldo_evidence", "Ingen SALDO-evidens (starkaste luckkandidaterna)"),
    )
    for classification, heading in headings:
        selected = [row for row in rows if row["classification"] == classification]
        lines.extend([heading + f" ({len(selected)}):"])
        for row in selected:
            lines.append(
                f"  {row['lemma']} | article_id={row['article_id']} | mode={row['variant_mode']}"
            )
            if row["orthographic_candidates"]:
                lines.append(
                    f"    Ortografi ({row['orthographic_kind']}): "
                    + ", ".join(row["orthographic_candidates"])
                )
            if row["saldo_form_overlap_count"]:
                lines.append(
                    f"    Formträffar i SALDO: {row['saldo_form_overlap_count']}/{row['saol_form_count']} "
                    f"({row['saldo_form_overlap_ratio']:.1%})"
                )
                lines.append(
                    "    Kandidatlemma via former: "
                    + (", ".join(row["form_evidence_candidate_lemmas"]) or "–")
                )
        lines.append("")
    return "\n".join(lines) + "\n"


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Classify missing SAOL noun article variants by independent evidence in the materialized SALDO artifact"
    )
    parser.add_argument("--alignment", type=Path, default=DEFAULT_ALIGNMENT)
    parser.add_argument("--saldo-forms", type=Path, default=DEFAULT_SALDO_FORMS)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    args = parser.parse_args()

    rows, summary = classify_missing_variants(_read_jsonl(args.alignment), read_saldo_forms(args.saldo_forms))
    _write_jsonl(args.jsonl, rows)
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render(rows, summary), encoding="utf-8")
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saknade variantparadigm: {summary['missing_variants']}")
    print(f"Klassningar: {summary['classification_counts']}")
    print(f"Ortografiska typer: {summary['orthographic_kind_counts']}")
    print(f"Text: {args.text}")
    print(f"JSONL: {args.jsonl}")


if __name__ == "__main__":
    main()
