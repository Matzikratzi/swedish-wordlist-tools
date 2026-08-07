from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable


def id_key(row: dict[str, Any]) -> tuple[str, str]:
    return (str(row.get("urspr_lopnr") or ""), str(row.get("subnr") or ""))


def is_plain_reference(row: dict[str, Any]) -> bool:
    """Return True for SAOL hänvisningsposter whose ordkl starts with `(hv)`.

    SAOL also annotates some references with information about the referenced
    form, for example `(hv) <i>komp.</i>` for `färre -> få`. The homonym
    number is deliberately ignored: reference entries can have homonr=0
    (inflected-form redirects), homonr=1 (`acne -> akne`) or higher numbers.
    """
    return str(row.get("ordkl") or "").strip().casefold().startswith("(hv)")


def _heading(row: dict[str, Any]) -> str:
    return str(row.get("ord") or row.get("stycke") or row.get("normaliserat_ord") or "").strip()


def materialize_heading_model(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(records)
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[id_key(row)].append(row)

    articles: list[dict[str, Any]] = []
    references: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []

    for key, peers in grouped.items():
        plain_refs = [row for row in peers if is_plain_reference(row)]
        lexical = [row for row in peers if not is_plain_reference(row)]

        # (hv) rows are redirect/reference records, independent of homonr.
        for row in plain_refs:
            references.append({
                "source_id": key[0],
                "subnr": key[1],
                "source_homonr": str(row.get("homonr") or ""),
                "heading": _heading(row),
                "target_normalised_word": str(row.get("normaliserat_ord") or ""),
                "ordkl": str(row.get("ordkl") or ""),
                "upos": str(row.get("upos") or ""),
                "text": str(row.get("text") or ""),
                "source": str(row.get("source") or ""),
            })

        if not lexical:
            continue

        nonzero = [row for row in lexical if str(row.get("homonr") or "") not in {"", "0"}]
        zero = [row for row in lexical if str(row.get("homonr") or "") == "0"]
        homonym_numbers = sorted({str(row.get("homonr") or "") for row in nonzero})

        if zero and len(homonym_numbers) != 1:
            unresolved.append({
                "kind": "ambiguous_zero_heading_anchor",
                "source_id": key[0],
                "subnr": key[1],
                "normalised_words": sorted({str(row.get("normaliserat_ord") or "") for row in lexical}),
                "nonzero_homonym_numbers": homonym_numbers,
                "zero_headings": [_heading(row) for row in zero],
            })

        by_homonym: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in nonzero:
            by_homonym[str(row.get("homonr") or "")].append(row)

        for homonr, homonym_rows in sorted(by_homonym.items(), key=lambda item: int(item[0]) if item[0].isdigit() else 999999):
            primary_headings = list(dict.fromkeys(_heading(row) for row in homonym_rows if _heading(row)))
            alternate_rows = zero if len(homonym_numbers) == 1 else []
            alternate_headings = list(dict.fromkeys(_heading(row) for row in alternate_rows if _heading(row)))
            articles.append({
                "source_id": key[0],
                "subnr": key[1],
                "normalised_word": str(homonym_rows[0].get("normaliserat_ord") or ""),
                "homonym_number": homonr,
                "primary_headings": primary_headings,
                "alternate_headings": alternate_headings,
                "headings": [
                    *({"heading": heading, "type": "primary"} for heading in primary_headings),
                    *({"heading": heading, "type": "alternate"} for heading in alternate_headings),
                ],
                "source_row_count": len(homonym_rows) + len(alternate_rows),
                "source_homonym_numbers": list(dict.fromkeys(str(row.get("homonr") or "") for row in [*homonym_rows, *alternate_rows])),
                "ordkl": str(homonym_rows[0].get("ordkl") or ""),
                "upos": str(homonym_rows[0].get("upos") or ""),
                "text": str(homonym_rows[0].get("text") or ""),
                "source": str(homonym_rows[0].get("source") or ""),
            })

        # A lexical homonr=0 without any non-zero lexical row cannot safely be
        # assigned to a homonym. Keep it visible instead of inventing an anchor.
        if zero and not nonzero:
            unresolved.append({
                "kind": "standalone_lexical_zero",
                "source_id": key[0],
                "subnr": key[1],
                "normalised_words": sorted({str(row.get("normaliserat_ord") or "") for row in zero}),
                "zero_headings": [_heading(row) for row in zero],
            })

    articles.sort(key=lambda row: (row["normalised_word"].casefold(), row["homonym_number"], row["source_id"]))
    references.sort(key=lambda row: (row["heading"].casefold(), row["source_id"]))
    unresolved.sort(key=lambda row: (row["kind"], row["source_id"]))
    return {"articles": articles, "references": references, "unresolved": unresolved}
