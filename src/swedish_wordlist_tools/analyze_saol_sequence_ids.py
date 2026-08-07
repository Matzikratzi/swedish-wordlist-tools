from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .jsonl import read_jsonl

DEFAULT_SAOL = Path("data/raw/saol14-faksimil.jsonl")
DEFAULT_TEXT = Path("reports/saol14-sequence-id-analysis.txt")
DEFAULT_JSON = Path("reports/saol14-sequence-id-analysis.json")


def _int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _homonr(row: dict[str, Any]) -> str:
    return str(row.get("homonr") or "")


def _lemma(row: dict[str, Any]) -> str:
    return str(row.get("normaliserat_ord") or "")


def _ord(row: dict[str, Any]) -> str:
    return str(row.get("ord") or "")


def _group_key(row: dict[str, Any]) -> tuple[int | None, int | None]:
    return (_int(row.get("urspr_lopnr")), _int(row.get("subnr")))


def _delta_counter(values: list[int]) -> Counter[int]:
    return Counter(b - a for a, b in zip(values, values[1:]))


def _counter_dict(counter: Counter[Any]) -> dict[str, int]:
    return {str(key): count for key, count in sorted(counter.items(), key=lambda item: (-item[1], str(item[0])))}


def analyze(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(records)
    numeric_rows = [row for row in rows if _int(row.get("urspr_lopnr")) is not None and _int(row.get("subnr")) is not None]

    raw_urspr = [_int(row.get("urspr_lopnr")) for row in numeric_rows]
    raw_subnr = [_int(row.get("subnr")) for row in numeric_rows]
    raw_urspr_int = [value for value in raw_urspr if value is not None]
    raw_subnr_int = [value for value in raw_subnr if value is not None]

    groups: dict[tuple[int | None, int | None], list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    group_order: list[tuple[int | None, int | None]] = []
    seen_groups: set[tuple[int | None, int | None]] = set()
    for index, row in enumerate(numeric_rows):
        key = _group_key(row)
        groups[key].append((index, row))
        if key not in seen_groups:
            seen_groups.add(key)
            group_order.append(key)

    distinct_urspr = [key[0] for key in group_order if key[0] is not None]
    distinct_subnr = [key[1] for key in group_order if key[1] is not None]

    homonr_patterns: Counter[str] = Counter()
    zero_anchor_counts: Counter[str] = Counter()
    zero_position_counts: Counter[str] = Counter()
    zero_groups_without_anchor: list[dict[str, Any]] = []
    zero_examples: list[dict[str, Any]] = []
    multirow_groups = 0

    for key in group_order:
        indexed_rows = groups[key]
        if len(indexed_rows) > 1:
            multirow_groups += 1
        homonrs = [_homonr(row) for _, row in indexed_rows]
        homonr_patterns[",".join(homonrs)] += 1
        for position, (global_index, row) in enumerate(indexed_rows):
            if _homonr(row) != "0":
                continue
            preceding_nonzero = [
                _homonr(previous_row)
                for _, previous_row in indexed_rows[:position]
                if _homonr(previous_row) not in {"", "0"}
            ]
            following_nonzero = [
                _homonr(next_row)
                for _, next_row in indexed_rows[position + 1 :]
                if _homonr(next_row) not in {"", "0"}
            ]
            if preceding_nonzero:
                anchor = preceding_nonzero[-1]
                relation = "after_same_group_nonzero"
            elif following_nonzero:
                anchor = following_nonzero[0]
                relation = "before_same_group_nonzero"
            else:
                anchor = "none"
                relation = "no_same_group_nonzero"
            zero_anchor_counts[anchor] += 1
            zero_position_counts[relation] += 1
            example = {
                "urspr_lopnr": key[0],
                "subnr": key[1],
                "anchor_homonr": anchor,
                "relation": relation,
                "lemma": _lemma(row),
                "ord": _ord(row),
                "group_homonrs": homonrs,
                "group_ords": [_ord(item) for _, item in indexed_rows],
                "raw_row_index": global_index,
            }
            if len(zero_examples) < 100:
                zero_examples.append(example)
            if anchor == "none" and len(zero_groups_without_anchor) < 100:
                zero_groups_without_anchor.append(example)

    raw_urspr_deltas = _delta_counter(raw_urspr_int)
    raw_subnr_deltas = _delta_counter(raw_subnr_int)
    distinct_urspr_deltas = _delta_counter(distinct_urspr)
    distinct_subnr_deltas = _delta_counter(distinct_subnr)

    gap_rows: list[dict[str, Any]] = []
    for previous_key, current_key in zip(group_order, group_order[1:]):
        pu, ps = previous_key
        cu, cs = current_key
        if pu is None or ps is None or cu is None or cs is None:
            continue
        gap_rows.append({
            "previous_urspr_lopnr": pu,
            "previous_subnr": ps,
            "urspr_lopnr": cu,
            "subnr": cs,
            "urspr_delta": cu - pu,
            "subnr_delta": cs - ps,
            "previous_lemma": _lemma(groups[previous_key][0][1]),
            "lemma": _lemma(groups[current_key][0][1]),
        })
    largest_positive_gaps = sorted(
        (row for row in gap_rows if row["urspr_delta"] > 0),
        key=lambda row: (row["urspr_delta"], row["subnr_delta"]),
        reverse=True,
    )[:50]

    equal_ids = sum(
        1
        for row in numeric_rows
        if _int(row.get("urspr_lopnr")) == _int(row.get("subnr"))
    )

    return {
        "rows": len(rows),
        "numeric_id_rows": len(numeric_rows),
        "urspr_equals_subnr_rows": equal_ids,
        "urspr_differs_from_subnr_rows": len(numeric_rows) - equal_ids,
        "article_id_groups": len(group_order),
        "multirow_id_groups": multirow_groups,
        "homonr_pattern_counts": _counter_dict(homonr_patterns),
        "homonr_zero_count": sum(zero_anchor_counts.values()),
        "homonr_zero_anchor_counts": _counter_dict(zero_anchor_counts),
        "homonr_zero_position_counts": _counter_dict(zero_position_counts),
        "raw_urspr_delta_counts": _counter_dict(raw_urspr_deltas),
        "raw_subnr_delta_counts": _counter_dict(raw_subnr_deltas),
        "distinct_group_urspr_delta_counts": _counter_dict(distinct_urspr_deltas),
        "distinct_group_subnr_delta_counts": _counter_dict(distinct_subnr_deltas),
        "raw_urspr_negative_deltas": sum(count for delta, count in raw_urspr_deltas.items() if delta < 0),
        "distinct_group_urspr_negative_deltas": sum(count for delta, count in distinct_urspr_deltas.items() if delta < 0),
        "largest_positive_group_gaps": largest_positive_gaps,
        "homonr_zero_examples": zero_examples,
        "homonr_zero_without_anchor_examples": zero_groups_without_anchor,
    }


def _top_delta_lines(title: str, values: dict[str, int], limit: int = 20) -> list[str]:
    lines = [title]
    for delta, count in list(values.items())[:limit]:
        lines.append(f"  Δ={delta:>6}: {count}")
    if not values:
        lines.append("  (inga)")
    return lines


def render(report: dict[str, Any]) -> str:
    lines = [
        f"Rå-rader: {report['rows']}",
        f"Rader med numeriska urspr_lopnr/subnr: {report['numeric_id_rows']}",
        f"urspr_lopnr == subnr: {report['urspr_equals_subnr_rows']}",
        f"urspr_lopnr != subnr: {report['urspr_differs_from_subnr_rows']}",
        f"Unika (urspr_lopnr, subnr)-grupper: {report['article_id_groups']}",
        f"Flerradsgrupper: {report['multirow_id_groups']}",
        "",
        f"homonr=0-rader: {report['homonr_zero_count']}",
        "Vilket icke-noll-homonr homonr=0 är kopplat till inom samma ID-grupp:",
    ]
    for anchor, count in report["homonr_zero_anchor_counts"].items():
        lines.append(f"  homonr {anchor}: {count}")
    lines.extend(["", "Position för homonr=0 inom samma ID-grupp:"])
    for relation, count in report["homonr_zero_position_counts"].items():
        lines.append(f"  {relation}: {count}")

    lines.extend(["", "Vanligaste homonr-sekvenser inom samma (urspr_lopnr, subnr):"])
    for pattern, count in list(report["homonr_pattern_counts"].items())[:30]:
        lines.append(f"  {pattern or '(tomt)'}: {count}")

    lines.extend([""] + _top_delta_lines("Rå rad-för-rad: urspr_lopnr-hopp", report["raw_urspr_delta_counts"]))
    lines.extend([""] + _top_delta_lines("Rå rad-för-rad: subnr-hopp", report["raw_subnr_delta_counts"]))
    lines.extend([""] + _top_delta_lines("Mellan första raden i varje ny ID-grupp: urspr_lopnr-hopp", report["distinct_group_urspr_delta_counts"]))
    lines.extend([""] + _top_delta_lines("Mellan första raden i varje ny ID-grupp: subnr-hopp", report["distinct_group_subnr_delta_counts"]))

    lines.extend([
        "",
        f"Negativa urspr_lopnr-hopp, råa rader: {report['raw_urspr_negative_deltas']}",
        f"Negativa urspr_lopnr-hopp, nya ID-grupper: {report['distinct_group_urspr_negative_deltas']}",
        "",
        "Största positiva hopp mellan nya ID-grupper:",
    ])
    for row in report["largest_positive_group_gaps"][:30]:
        lines.append(
            f"  Δurspr={row['urspr_delta']}, Δsubnr={row['subnr_delta']}: "
            f"{row['previous_urspr_lopnr']} {row['previous_lemma']} -> "
            f"{row['urspr_lopnr']} {row['lemma']}"
        )

    lines.extend(["", "Exempel på homonr=0 och dess ankare:"])
    for row in report["homonr_zero_examples"][:50]:
        lines.append(
            f"  {row['lemma']} | id={row['urspr_lopnr']}/{row['subnr']} | "
            f"homonr-sekvens={','.join(row['group_homonrs'])} | "
            f"ankare={row['anchor_homonr']} | ord={row['ord']}"
        )

    if report["homonr_zero_without_anchor_examples"]:
        lines.extend(["", "homonr=0 utan något icke-noll-homonr i samma ID-grupp:"])
        for row in report["homonr_zero_without_anchor_examples"][:50]:
            lines.append(
                f"  {row['lemma']} | id={row['urspr_lopnr']}/{row['subnr']} | ord={row['ord']}"
            )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analysera SAOL-råfilens urspr_lopnr/subnr-sekvenser och hur homonr=0 är förankrat"
    )
    parser.add_argument("saol", nargs="?", type=Path, default=DEFAULT_SAOL)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()

    report = analyze(read_jsonl(args.saol))
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render(report), encoding="utf-8")
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Rå-rader: {report['rows']}")
    print(f"ID-grupper: {report['article_id_groups']}")
    print(f"homonr=0: {report['homonr_zero_count']}")
    print(f"homonr=0-ankare: {report['homonr_zero_anchor_counts']}")
    print(f"Text: {args.text}")
    print(f"JSON: {args.json}")


if __name__ == "__main__":
    main()
