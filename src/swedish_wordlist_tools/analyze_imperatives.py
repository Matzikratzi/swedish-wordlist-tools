from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from .compare_sources import read_saldo
from .jsonl import read_jsonl
from .verb_game_fallback import interpret_playable_verb_slots

DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_SALDO = Path("data/raw/saldom.xml")
DEFAULT_TEXT = Path("reports/saol14-imperatives.txt")
DEFAULT_JSON = Path("reports/saol14-imperatives.json")

_IMPERATIVE_SEGMENT_RE = re.compile(r"\bimper\.\s*(?P<body>[^,;_]*)", re.IGNORECASE)
_FORM_RE = re.compile(r"[+\-]?[A-Za-zÅÄÖåäöÉéÜü]+(?:-[A-Za-zÅÄÖåäöÉéÜü]+)*")
_MARKER_WORDS = {"el", "eller", "vard", "åld", "prov", "ibl", "och", "obrukl"}


def _first_word(lemma: str) -> str:
    return lemma.partition(" ")[0]


def _preterite_forms(slots: Any) -> tuple[str, ...]:
    if slots is None:
        return ()
    return tuple(form.partition(" ")[0] for form in slots.forms_for("preterite"))


def generate_imperative(lemma: str, slots: Any) -> tuple[str | None, str]:
    """Generate one conservative imperative candidate and name the rule."""
    if " " in lemma.strip():
        return None, "multiword_lemma"
    word = lemma.casefold().strip()
    if not word or not word.isalpha():
        return None, "not_single_alpha_head"
    if not word.endswith("a"):
        return word, "non_a_infinitive"
    preterites = _preterite_forms(slots)
    if any(form.casefold().endswith("ade") for form in preterites):
        return word, "class1_preterite_ade"
    if len(word) <= 2:
        return word, "short_a_infinitive"
    return word[:-1], "drop_final_a"


def _apply_explicit_token(lemma: str, token: str) -> str | None:
    head = _first_word(lemma).casefold()
    token = token.casefold()
    if token.startswith("+"):
        return head + token[1:]
    if token.startswith("-"):
        suffix = token[1:]
        if not suffix:
            return None
        for start in range(len(head)):
            if head[start:].startswith(suffix[:1]):
                return head[:start] + suffix
        return None
    return token


def explicit_saol_imperatives(record: dict[str, Any]) -> tuple[str, ...]:
    text = str(record.get("text") or "")
    match = _IMPERATIVE_SEGMENT_RE.search(text)
    if match is None:
        return ()
    body = match.group("body").strip()
    token_matches = list(_FORM_RE.finditer(body))
    lemma = str(record.get("normaliserat_ord") or "").strip()
    result: list[str] = []
    for index, token_match in enumerate(token_matches):
        token = token_match.group(0)
        if token.casefold().lstrip("+-") in _MARKER_WORDS:
            continue
        # Only the final alphabetic token is unsafe when the 50-char field ends
        # inside the imperative segment. Earlier complete alternatives remain.
        if (
            len(text) == 50
            and match.end() == len(text)
            and index == len(token_matches) - 1
            and token_match.end() == len(body)
            and body
            and body[-1].isalpha()
        ):
            continue
        written = _apply_explicit_token(lemma, token)
        if written and written.isalpha() and written not in result:
            result.append(written)
    return tuple(result)


def _saldo_verb_forms(saldo: dict[str, list[dict[str, Any]]], lemma: str) -> set[str]:
    forms: set[str] = set()
    for analysis in saldo.get(lemma.casefold(), ()):
        if analysis.get("upos") == "VERB":
            forms.update(str(form).casefold() for form in analysis.get("forms", ()))
    return forms


def build_report(saol_path: Path = DEFAULT_SAOL, saldo_path: Path = DEFAULT_SALDO) -> dict[str, Any]:
    saldo = read_saldo(saldo_path)
    rows: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    rule_counts: Counter[str] = Counter()

    for record in read_jsonl(saol_path):
        if str(record.get("upos", "")).upper() != "VERB":
            continue
        lemma = str(record.get("normaliserat_ord") or "").strip()
        playable = interpret_playable_verb_slots(record)
        candidate, rule = generate_imperative(lemma, playable)
        explicit = explicit_saol_imperatives(record)
        saldo_forms = _saldo_verb_forms(saldo, lemma)
        rule_counts[rule] += 1

        if candidate is None:
            status = "not_generated"
        elif candidate in saldo_forms:
            status = "generated_in_saldo"
        elif saldo_forms:
            status = "generated_missing_from_matched_saldo"
        else:
            status = "no_exact_saldo_verb_lemma"
        counts[status] += 1

        explicit_status = "none"
        if explicit:
            explicit_status = (
                "generated_matches_explicit_saol"
                if candidate in explicit
                else "generated_differs_from_explicit_saol"
            )
            counts[explicit_status] += 1

        rows.append({
            "lemma": lemma,
            "homonr": str(record.get("homonr") or ""),
            "rule": rule,
            "generated": candidate,
            "status": status,
            "explicit_saol": list(explicit),
            "explicit_status": explicit_status,
            "generated_in_saldo": bool(candidate and candidate in saldo_forms),
            "saldo_forms_sample": sorted(saldo_forms)[:30],
            "text": str(record.get("text") or ""),
        })

    rows.sort(key=lambda row: (row["status"], row["explicit_status"], row["lemma"], row["homonr"]))
    generated = sum(1 for row in rows if row["generated"])
    in_saldo = counts["generated_in_saldo"]
    saldo_checkable = in_saldo + counts["generated_missing_from_matched_saldo"]
    explicit_total = sum(1 for row in rows if row["explicit_saol"])
    explicit_matches = counts["generated_matches_explicit_saol"]
    return {
        "verb_records": len(rows),
        "generated_candidates": generated,
        "generated_in_saldo": in_saldo,
        "saldo_checkable_candidates": saldo_checkable,
        "generated_in_saldo_percent": round(100 * in_saldo / saldo_checkable, 2) if saldo_checkable else 0.0,
        "explicit_saol_records": explicit_total,
        "explicit_match_percent": round(100 * explicit_matches / explicit_total, 2) if explicit_total else 0.0,
        "status_counts": dict(counts.most_common()),
        "rule_counts": dict(rule_counts.most_common()),
        "records": rows,
        "note": "SALDO is validation only; absence from SALDO does not reject a SAOL-derived candidate.",
    }


def render_text(report: dict[str, Any]) -> str:
    lines = [
        f"Verbposter: {report['verb_records']}",
        f"Genererade imperativkandidater: {report['generated_candidates']}",
        f"Kandidater med exakt SALDO-verblemma: {report['saldo_checkable_candidates']}",
        f"Kandidater belagda i SALDO: {report['generated_in_saldo']} ({report['generated_in_saldo_percent']:.2f} % av kontrollerbara)",
        f"Poster med uttryckligt SAOL-imperativ: {report['explicit_saol_records']}",
        f"Överensstämmelse med uttryckligt SAOL-imperativ: {report['explicit_match_percent']:.2f} %",
        "", "Status:",
    ]
    for key, count in report["status_counts"].items():
        lines.append(f"  {count:6d}  {key}")
    lines.extend(["", "Regler:"])
    for key, count in report["rule_counts"].items():
        lines.append(f"  {count:6d}  {key}")

    def section(title: str, status: str, limit: int = 100) -> None:
        lines.extend(["", title + ":"])
        selected = [row for row in report["records"] if row.get("explicit_status") == status or row.get("status") == status][:limit]
        for row in selected:
            lines.append(
                f"  {row['lemma']} (homonr={row['homonr']}) -> {row['generated']} "
                f"| rule={row['rule']} | status={row['status']} | explicit={row['explicit_saol']}"
            )
        if not selected:
            lines.append("  (inga)")

    section("Avviker från uttryckligt SAOL-imperativ", "generated_differs_from_explicit_saol")
    section("Genererad men saknas hos exakt matchat SALDO-verb", "generated_missing_from_matched_saldo")
    section("Ingen exakt SALDO-verblemmaträff", "no_exact_saldo_verb_lemma")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit generated SAOL14 imperatives against SALDO")
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("saldo", nargs="?", type=Path, default=DEFAULT_SALDO)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()
    report = build_report(args.saol, args.saldo)
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render_text(report), encoding="utf-8")
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Verbposter: {report['verb_records']}")
    print(f"Genererade kandidater: {report['generated_candidates']}")
    print(f"Belagda i SALDO: {report['generated_in_saldo']} ({report['generated_in_saldo_percent']:.2f} % av kontrollerbara)")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
