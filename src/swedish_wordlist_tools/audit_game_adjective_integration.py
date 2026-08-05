from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

from .game_wordlist import (
    DEFAULT_ADJECTIVE_FORMS,
    DEFAULT_INPUT,
    DEFAULT_SALDO,
    canonical_adjective_forms,
    filter_game_words,
    normalise_game_word,
    standalone_saldo_forms,
)

DEFAULT_ADJUDICATION = Path("reports/saol14-adjective-final-adjudication.jsonl")
DEFAULT_TEXT = Path("reports/saol14-game-adjective-integration-audit.txt")
DEFAULT_JSON = Path("reports/saol14-game-adjective-integration-audit.json")
DEFAULT_ADDED = Path("reports/saol14-game-adjective-added-words.txt")

CONFIRMED_GAP_STATUSES = {
    "confirmed_saldo_form_gap",
    "confirmed_saldo_adjective_analysis_gap",
}


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def confirmed_gap_forms(path: Path) -> set[str]:
    result: set[str] = set()
    if not path.exists():
        return result
    for row in read_jsonl(path):
        if row.get("final_adjudication") not in CONFIRMED_GAP_STATUSES:
            continue
        word = normalise_game_word(str(row.get("written_form") or ""))
        if word is not None:
            result.add(word)
    return result


def build_audit(
    input_path: Path = DEFAULT_INPUT,
    saldo_path: Path = DEFAULT_SALDO,
    adjective_forms_path: Path = DEFAULT_ADJECTIVE_FORMS,
    adjudication_path: Path = DEFAULT_ADJUDICATION,
) -> tuple[dict[str, Any], list[str]]:
    source_lines = input_path.read_text(encoding="utf-8").splitlines()
    saldo_forms = standalone_saldo_forms(saldo_path)
    adjective_forms = canonical_adjective_forms(adjective_forms_path)

    baseline_words, _baseline_counts = filter_game_words(source_lines, saldo_forms)
    integrated_words, _integrated_counts = filter_game_words(
        [*source_lines, *sorted(adjective_forms, key=str.casefold)],
        saldo_forms | adjective_forms,
    )

    baseline = set(baseline_words)
    integrated = set(integrated_words)
    added = sorted(integrated - baseline)
    removed = sorted(baseline - integrated)
    unexpected_added = sorted(set(added) - adjective_forms)
    canonical_not_added = sorted(adjective_forms & baseline)

    confirmed = confirmed_gap_forms(adjudication_path)
    confirmed_present = sorted(confirmed & integrated)
    confirmed_missing = sorted(confirmed - integrated)

    report: dict[str, Any] = {
        "baseline_game_words": len(baseline),
        "integrated_game_words": len(integrated),
        "added_game_words": len(added),
        "removed_game_words": len(removed),
        "canonical_adjective_forms": len(adjective_forms),
        "canonical_adjective_forms_already_in_baseline": len(canonical_not_added),
        "unexpected_added_words": len(unexpected_added),
        "confirmed_gap_forms": len(confirmed),
        "confirmed_gap_forms_present": len(confirmed_present),
        "confirmed_gap_forms_missing": len(confirmed_missing),
        "integration_is_clean": (
            not removed and not unexpected_added and not confirmed_missing
        ),
        "removed_examples": removed[:50],
        "unexpected_added_examples": unexpected_added[:50],
        "confirmed_gap_forms_missing_examples": confirmed_missing[:50],
        "added_examples": added[:100],
        "source": str(input_path),
        "saldo": str(saldo_path),
        "canonical_adjective_artifact": str(adjective_forms_path),
        "final_adjudication": str(adjudication_path),
    }
    return report, added


def render_text(report: dict[str, Any]) -> str:
    status = "REN" if report["integration_is_clean"] else "KRÄVER GRANSKNING"
    lines = [
        f"Integrationsstatus: {status}",
        f"Ord före adjektivartefakten: {report['baseline_game_words']}",
        f"Ord efter adjektivartefakten: {report['integrated_game_words']}",
        f"Tillagda ord: {report['added_game_words']}",
        f"Borttagna ord: {report['removed_game_words']}",
        f"Kanoniska adjektivformer: {report['canonical_adjective_forms']}",
        (
            "Kanoniska adjektivformer som redan fanns: "
            f"{report['canonical_adjective_forms_already_in_baseline']}"
        ),
        f"Oväntat tillagda ord: {report['unexpected_added_words']}",
        f"Bekräftade SALDO-luckor: {report['confirmed_gap_forms']}",
        (
            "Bekräftade SALDO-luckor i spelordlistan: "
            f"{report['confirmed_gap_forms_present']}"
        ),
        (
            "Bekräftade SALDO-luckor som saknas: "
            f"{report['confirmed_gap_forms_missing']}"
        ),
    ]
    for key, title in (
        ("removed_examples", "Borttagna ord"),
        ("unexpected_added_examples", "Oväntat tillagda ord"),
        ("confirmed_gap_forms_missing_examples", "Saknade bekräftade luckor"),
        ("added_examples", "Exempel på tillagda adjektivformer"),
    ):
        values = report.get(key) or []
        if values:
            lines.extend(["", f"{title}:"])
            lines.extend(f"  {value}" for value in values)
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit the canonical adjective artifact's effect on the game wordlist"
    )
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--saldo", type=Path, default=DEFAULT_SALDO)
    parser.add_argument("--adjective-forms", type=Path, default=DEFAULT_ADJECTIVE_FORMS)
    parser.add_argument("--adjudication", type=Path, default=DEFAULT_ADJUDICATION)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--added", type=Path, default=DEFAULT_ADDED)
    args = parser.parse_args()

    report, added = build_audit(
        args.input,
        args.saldo,
        args.adjective_forms,
        args.adjudication,
    )
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render_text(report), encoding="utf-8")
    args.json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.added.write_text("\n".join(added) + ("\n" if added else ""), encoding="utf-8")

    print(f"Integrationsstatus: {'REN' if report['integration_is_clean'] else 'KRÄVER GRANSKNING'}")
    print(f"Tillagda ord: {report['added_game_words']}")
    print(f"Bekräftade SALDO-luckor med: {report['confirmed_gap_forms_present']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")
    print(f"Tillagda ord: {args.added}")


if __name__ == "__main__":
    main()
