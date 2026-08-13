from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .artifact_paths import SAOL14_GAMEWORDS
from .build_final_wordlist import normalise_game_word, rejection_reason
from .jsonl import read_jsonl
from .saldo import NON_STANDALONE_MSD, SaldoAnalysis, read_saldo_analyses
from .saol_surface import clean_saol_word
from .saol_wordclasses import classes_from_record


DEFAULT_GAMEWORDS = SAOL14_GAMEWORDS
DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_SALDO = Path("data/raw/saldom.xml")
DEFAULT_TEXT = Path("reports/saol14-gamewords-vs-saldo.txt")
DEFAULT_JSON = Path("reports/saol14-gamewords-vs-saldo.json")
DEFAULT_ONLY_SAOL = Path("reports/saol14-gamewords-only-saol14.txt")
DEFAULT_ONLY_SALDO = Path("reports/saol14-gamewords-only-saldo.txt")
DEFAULT_CANDIDATES = Path("reports/saol14-gamewords-saldo-review-candidates.jsonl")


def _playable(value: str) -> str | None:
    word = normalise_game_word(value)
    return word if rejection_reason(word) is None else None


def _unique_analyses(path: Path) -> Iterable[SaldoAnalysis]:
    seen: set[int] = set()
    for analyses in read_saldo_analyses(path).values():
        for analysis in analyses:
            marker = id(analysis)
            if marker not in seen:
                seen.add(marker)
                yield analysis


def saldo_standalone_index(
    analyses: Iterable[SaldoAnalysis],
    candidate_classes: dict[str, set[str]] | None = None,
    final_forms: set[str] | None = None,
) -> tuple[set[str], dict[str, list[dict[str, Any]]]]:
    forms: set[str] = set()
    evidence: dict[str, list[dict[str, Any]]] = {}
    for analysis in analyses:
        lemma_keys = sorted({word for lemma in analysis.lemmas if (word := _playable(lemma))})
        items = [(lemma, "lemma") for lemma in analysis.lemmas]
        items.extend(
            (form.written_form, str(form.msd))
            for form in analysis.word_forms
            if str(form.msd).casefold() not in NON_STANDALONE_MSD
        )
        for raw_form, msd in items:
            word = _playable(raw_form)
            if word is None:
                continue
            forms.add(word)
            if candidate_classes is not None:
                same_class = any(
                    analysis.upos in candidate_classes.get(lemma, set())
                    for lemma in lemma_keys
                )
                if not same_class:
                    continue
            if final_forms is not None and word in final_forms:
                continue
            evidence.setdefault(word, []).append({
                "entry_id": analysis.entry_id,
                "upos": analysis.upos,
                "lemmas": lemma_keys,
                "msd": msd,
            })
    return forms, evidence


def saol_lemma_index(
    records: Iterable[dict[str, Any]],
) -> tuple[dict[str, set[str]], dict[str, list[dict[str, Any]]]]:
    classes: dict[str, set[str]] = {}
    articles: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        record_classes = classes_from_record(record)
        for key in ("ord", "normaliserat_ord"):
            lemma = clean_saol_word(record.get(key))
            word = _playable(lemma)
            if word is not None:
                classes.setdefault(word, set()).update(record_classes)
                item = {
                    "record_id": str(record.get("id") or record.get("subnr") or record.get("urspr_lopnr") or ""),
                    "upos": sorted(record_classes),
                    "ordkl": str(record.get("ordkl") or ""),
                    "notation": str(record.get("text") or ""),
                }
                if item not in articles.setdefault(word, []):
                    articles[word].append(item)
    return classes, articles


def _evidence_category(msd: str) -> str:
    value = msd.casefold()
    if "s-form" in value:
        return "S_FORM"
    if value.startswith(("pres_part", "pret_part")):
        return "PARTICIPLE"
    if value.startswith(("komp", "super")):
        return "COMPARISON"
    if " gen" in f" {value}":
        return "GENITIVE"
    return "CORE_INFLECTION"


_CATEGORY_PRIORITY = (
    "CORE_INFLECTION", "S_FORM", "PARTICIPLE", "COMPARISON", "GENITIVE"
)


def audit(
    game_words: Iterable[str],
    analyses: Iterable[SaldoAnalysis],
    saol_classes: dict[str, set[str]],
    saol_articles: dict[str, list[dict[str, Any]]] | None = None,
) -> tuple[dict[str, Any], list[str], list[str], list[dict[str, Any]]]:
    final = {word for value in game_words if (word := _playable(value))}
    saldo, evidence = saldo_standalone_index(
        analyses, candidate_classes=saol_classes, final_forms=final
    )
    only_saol = sorted(final - saldo)
    only_saldo = sorted(saldo - final)
    candidates: list[dict[str, Any]] = []
    category_counts: Counter[str] = Counter()
    for form in only_saldo:
        matching = evidence.get(form, [])
        if not matching:
            continue
        categories = sorted(
            {_evidence_category(str(item.get("msd") or "")) for item in matching}
        )
        primary = next(category for category in _CATEGORY_PRIORITY if category in categories)
        lemmas = sorted({lemma for item in matching for lemma in item.get("lemmas", [])})
        matching_articles = [
            article
            for lemma in lemmas
            for article in (saol_articles or {}).get(lemma, [])
            if set(article["upos"]) & {str(item.get("upos") or "") for item in matching}
        ]
        category_counts[primary] += 1
        candidates.append({
            "form": form,
            "status": "REVIEW_ONLY_SALDO_FORM_WITH_SAOL_LEMMA_AND_UPOS",
            "primary_category": primary,
            "categories": categories,
            "matching_saol_articles": matching_articles,
            "matching_saldo_analyses": matching,
        })

    summary = {
        "audit_only": True,
        "affects_game_wordlist": False,
        "authority": "SAOL14",
        "final_game_words": len(final),
        "saldo_standalone_forms": len(saldo),
        "shared_forms": len(final & saldo),
        "only_saol14": len(only_saol),
        "only_saldo": len(only_saldo),
        "saldo_only_with_exact_saol_lemma_and_upos_candidates": len(candidates),
        "review_candidates_by_primary_category": dict(sorted(category_counts.items())),
        "candidate_interpretation": (
            "Review signal only: exact lemma and word-class overlap do not prove that a "
            "SALDO-only form belongs in the SAOL14-derived output."
        ),
    }
    return summary, only_saol, only_saldo, candidates


def _write_lines(path: Path, values: Iterable[str]) -> None:
    rows = list(values)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(rows) + ("\n" if rows else ""), encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def run_audit(
    gamewords_path: Path = DEFAULT_GAMEWORDS,
    saol_path: Path = DEFAULT_SAOL,
    saldo_path: Path = DEFAULT_SALDO,
    text_path: Path = DEFAULT_TEXT,
    json_path: Path = DEFAULT_JSON,
    only_saol_path: Path = DEFAULT_ONLY_SAOL,
    only_saldo_path: Path = DEFAULT_ONLY_SALDO,
    candidates_path: Path = DEFAULT_CANDIDATES,
) -> dict[str, Any]:
    saol_classes, saol_articles = saol_lemma_index(read_jsonl(saol_path))
    summary, only_saol, only_saldo, candidates = audit(
        gamewords_path.read_text(encoding="utf-8").splitlines(),
        _unique_analyses(saldo_path),
        saol_classes,
        saol_articles,
    )
    report = {
        "gamewords": str(gamewords_path),
        "saol": str(saol_path),
        "saldo": str(saldo_path),
        "only_saol14_file": str(only_saol_path),
        "only_saldo_file": str(only_saldo_path),
        "review_candidates_file": str(candidates_path),
        **summary,
    }
    _write_lines(only_saol_path, only_saol)
    _write_lines(only_saldo_path, only_saldo)
    _write_jsonl(candidates_path, candidates)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    text_path.parent.mkdir(parents=True, exist_ok=True)
    text_path.write_text(
        "\n".join([
            "SAOL14-spelordlista jämförd med SALDO (endast audit)",
            "",
            "SALDO påverkar inte spelordlistan.",
            f"Spelord: {report['final_game_words']}",
            f"Fristående SALDO-former: {report['saldo_standalone_forms']}",
            f"Gemensamma: {report['shared_forms']}",
            f"Endast SAOL14: {report['only_saol14']}",
            f"Endast SALDO: {report['only_saldo']}",
            f"Granskningskandidater med exakt SAOL-lemma och ordklass: {report['saldo_only_with_exact_saol_lemma_and_upos_candidates']}",
            "Kandidater efter primärkategori: " + ", ".join(
                f"{key}={value}"
                for key, value in report["review_candidates_by_primary_category"].items()
            ),
            "",
            str(report["candidate_interpretation"]),
        ]) + "\n",
        encoding="utf-8",
    )
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare the final SAOL14-only game wordlist with SALDO without changing it."
    )
    parser.add_argument("--gamewords", type=Path, default=DEFAULT_GAMEWORDS)
    parser.add_argument("--saol", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--saldo", type=Path, default=DEFAULT_SALDO)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--only-saol", type=Path, default=DEFAULT_ONLY_SAOL)
    parser.add_argument("--only-saldo", type=Path, default=DEFAULT_ONLY_SALDO)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = run_audit(
        args.gamewords, args.saol, args.saldo, args.text, args.json,
        args.only_saol, args.only_saldo, args.candidates,
    )
    print("SALDO-audit klar; spelordlistan ändrades inte.")
    print(f"Gemensamma former: {report['shared_forms']}")
    print(f"Endast SAOL14: {report['only_saol14']}")
    print(f"Endast SALDO: {report['only_saldo']}")
    print(f"Granskningskandidater: {report['saldo_only_with_exact_saol_lemma_and_upos_candidates']}")
    print(f"Rapport: {args.text}")


if __name__ == "__main__":
    main()
