from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

from .artifact_paths import SAOL14_GAMEWORDS
from .build_final_wordlist import normalise_game_word, rejection_reason
from .jsonl import read_jsonl
from .saldo import SaldoAnalysis, read_saldo_analyses
from .saol_surface import clean_saol_word


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
    candidate_lemmas: set[str] | None = None,
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
            if str(form.msd).casefold() not in {"ci", "cm", "sms"}
        )
        for raw_form, msd in items:
            word = _playable(raw_form)
            if word is None:
                continue
            forms.add(word)
            if candidate_lemmas is not None and not set(lemma_keys) & candidate_lemmas:
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


def saol_lemma_keys(records: Iterable[dict[str, Any]]) -> set[str]:
    result: set[str] = set()
    for record in records:
        for key in ("ord", "normaliserat_ord"):
            lemma = clean_saol_word(record.get(key))
            word = _playable(lemma)
            if word is not None:
                result.add(word)
    return result


def audit(
    game_words: Iterable[str],
    analyses: Iterable[SaldoAnalysis],
    saol_lemmas: set[str],
) -> tuple[dict[str, Any], list[str], list[str], list[dict[str, Any]]]:
    final = {word for value in game_words if (word := _playable(value))}
    saldo, evidence = saldo_standalone_index(
        analyses, candidate_lemmas=saol_lemmas, final_forms=final
    )
    only_saol = sorted(final - saldo)
    only_saldo = sorted(saldo - final)
    candidates: list[dict[str, Any]] = []
    for form in only_saldo:
        matching = evidence.get(form, [])
        if not matching:
            continue
        candidates.append({
            "form": form,
            "status": "REVIEW_ONLY_SALDO_FORM_WITH_SAOL_LEMMA",
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
        "saldo_only_with_exact_saol_lemma_candidates": len(candidates),
        "candidate_interpretation": (
            "Review signal only: an exact lemma overlap does not prove that a SALDO-only "
            "form belongs in the SAOL14-derived output."
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
    summary, only_saol, only_saldo, candidates = audit(
        gamewords_path.read_text(encoding="utf-8").splitlines(),
        _unique_analyses(saldo_path),
        saol_lemma_keys(read_jsonl(saol_path)),
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
            f"Granskningskandidater med exakt SAOL-lemma: {report['saldo_only_with_exact_saol_lemma_candidates']}",
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
    print(f"Granskningskandidater: {report['saldo_only_with_exact_saol_lemma_candidates']}")
    print(f"Rapport: {args.text}")


if __name__ == "__main__":
    main()
