from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .analyze_imperatives import DEFAULT_SALDO, read_saldo_form_labels
from .analyze_verb_notation_inventory import DEFAULT_SAOL
from .jsonl import read_jsonl
from .saol_notation import parse_form_operations, split_alternative_branches
from .saol_source_policy import inflection_text, is_truncated_inflection_source
from .verb_shared_lexeme import realize_verb_operation

DEFAULT_TEXT = Path("reports/saol14-verb-positional-semantics.txt")
DEFAULT_JSON = Path("reports/saol14-verb-positional-semantics.json")

_PUNCTUATION = frozenset({",", ";"})
_ALTERNATIVE_MARKERS = frozenset({"el.", "h", "ibl."})


def pure_unlabelled_form_tokens(tokens: tuple[str, ...]) -> tuple[str, ...] | None:
    """Return form atoms only for a purely positional, unlabelled branch.

    This audit intentionally excludes labels, editorial prose and alternative
    markers.  We want SALDO to tell us what *position* means when SAOL gives no
    grammatical label at all, without mixing in cases whose slot is already
    stated explicitly.
    """

    result: list[str] = []
    for token in tokens:
        if token in _PUNCTUATION:
            continue
        if token.casefold() in _ALTERNATIVE_MARKERS:
            return None
        operations = parse_form_operations(token)
        if operations is None:
            return None
        # Optional spelling variants inside one source token still denote one
        # positional atom.  Keep the source token once; realization below emits
        # every spelling variant separately.
        result.append(token)
    return tuple(result) if result else None


def _saldo_labels_for_form(
    labels: dict[str, dict[str, set[str]]], lemma: str, form: str
) -> tuple[str, ...]:
    return tuple(sorted(labels.get(lemma.casefold(), {}).get(form.casefold(), set()), key=str.casefold))


def analyze(
    records: list[dict[str, Any]],
    saldo_labels: dict[str, dict[str, set[str]]],
) -> dict[str, Any]:
    branch_counts: Counter[int] = Counter()
    position_label_counts: dict[int, dict[int, Counter[str]]] = defaultdict(
        lambda: defaultdict(Counter)
    )
    position_forms_with_labels: Counter[tuple[int, int]] = Counter()
    position_forms_without_labels: Counter[tuple[int, int]] = Counter()
    examples: dict[int, list[dict[str, Any]]] = defaultdict(list)

    for record in records:
        if str(record.get("upos") or "").upper() != "VERB":
            continue
        if is_truncated_inflection_source(record):
            continue
        lemma = str(record.get("normaliserat_ord") or "").strip()
        pattern = inflection_text(record)
        if not lemma or pattern is None:
            continue

        branches = split_alternative_branches(pattern)
        for branch in branches:
            atoms = pure_unlabelled_form_tokens(branch.tokens)
            if atoms is None:
                continue
            atom_count = len(atoms)
            branch_counts[atom_count] += 1
            row_positions: list[dict[str, Any]] = []

            for position, token in enumerate(atoms, start=1):
                operations = parse_form_operations(token)
                assert operations is not None
                realised: list[dict[str, Any]] = []
                for operation in operations:
                    written = realize_verb_operation(lemma, operation)
                    if written is None:
                        realised.append(
                            {
                                "token": token,
                                "written_form": None,
                                "saldo_labels": [],
                            }
                        )
                        continue
                    raw_labels = _saldo_labels_for_form(saldo_labels, lemma, written)
                    if raw_labels:
                        position_forms_with_labels[(atom_count, position)] += 1
                        position_label_counts[atom_count][position].update(raw_labels)
                    else:
                        position_forms_without_labels[(atom_count, position)] += 1
                    realised.append(
                        {
                            "token": token,
                            "written_form": written,
                            "saldo_labels": list(raw_labels),
                        }
                    )
                row_positions.append(
                    {
                        "position": position,
                        "source_token": token,
                        "realizations": realised,
                    }
                )

            if len(examples[atom_count]) < 25:
                examples[atom_count].append(
                    {
                        "lemma": lemma,
                        "homonym_number": str(record.get("homonr") or ""),
                        "text": branch.text,
                        "positions": row_positions,
                    }
                )

    groups: list[dict[str, Any]] = []
    for atom_count, count in sorted(branch_counts.items()):
        positions: list[dict[str, Any]] = []
        for position in range(1, atom_count + 1):
            label_counts = position_label_counts[atom_count][position]
            positions.append(
                {
                    "position": position,
                    "forms_with_saldo_labels": position_forms_with_labels[(atom_count, position)],
                    "forms_without_saldo_labels": position_forms_without_labels[(atom_count, position)],
                    "saldo_label_counts": dict(label_counts.most_common()),
                }
            )
        groups.append(
            {
                "atom_count": atom_count,
                "branches": count,
                "positions": positions,
                "examples": examples[atom_count],
            }
        )

    return {
        "pure_unlabelled_branches": sum(branch_counts.values()),
        "branch_counts_by_atom_count": {str(k): v for k, v in sorted(branch_counts.items())},
        "groups": groups,
    }


def render(summary: dict[str, Any]) -> str:
    lines = [
        "SAOL14 VERB: positionssemantik kontrollerad mot SALDO-MSD",
        "",
        "Endast kompletta, helt oetiketterade brancher ingår. Trunkerade 49/50-rader,",
        "alternativmarkörer och explicit etiketterade former är exkluderade. SALDO används",
        "bara som extern kontroll av vad respektive position verkar betyda.",
        "",
        f"Rena oetiketterade brancher: {summary['pure_unlabelled_branches']}",
        "Atomantal: " + ", ".join(
            f"{key}={value}" for key, value in summary["branch_counts_by_atom_count"].items()
        ),
    ]

    for group in summary["groups"]:
        lines.extend(("", f"=== {group['atom_count']} atomer: {group['branches']} brancher ==="))
        for position in group["positions"]:
            lines.append(
                f"Position {position['position']}: "
                f"med SALDO-etikett={position['forms_with_saldo_labels']}, "
                f"utan={position['forms_without_saldo_labels']}"
            )
            for label, count in list(position["saldo_label_counts"].items())[:20]:
                lines.append(f"  {count:6d}  {label}")

        lines.append("Exempel:")
        for example in group["examples"][:12]:
            hom = f" ({example['homonym_number']})" if example["homonym_number"] else ""
            lines.append(f"  {example['lemma']}{hom} | {example['text']}")
            for position in example["positions"]:
                for realization in position["realizations"]:
                    labels = ", ".join(realization["saldo_labels"]) or "-"
                    lines.append(
                        f"    p{position['position']} {position['source_token']} -> "
                        f"{realization['written_form'] or '?'} | SALDO: {labels}"
                    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit unlabelled SAOL verb atom positions against raw SALDO MSD labels"
    )
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--saldo", type=Path, default=DEFAULT_SALDO)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()

    labels, _observed = read_saldo_form_labels(args.saldo)
    summary = analyze(read_jsonl(args.saol), labels)
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render(summary), encoding="utf-8")
    args.json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Rena oetiketterade brancher: {summary['pure_unlabelled_branches']}")
    print("Atomantal:")
    for atom_count, count in summary["branch_counts_by_atom_count"].items():
        print(f"  {atom_count}: {count}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
