from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .classify_form_mismatches import DEFAULT_JSONL as DEFAULT_CLASSIFICATIONS, UNCLASSIFIED

DEFAULT_JSONL = Path("reports/saol14-form-mismatch-classification-audit.jsonl")
DEFAULT_SUMMARY = Path("reports/saol14-form-mismatch-classification-audit-summary.json")
DEFAULT_TEXT = Path("reports/saol14-form-mismatch-classification-audit.txt")
GAMEWORD_BASENAME = "saol14-gamewords.txt"
GAMEWORD_CANDIDATES = (
    Path("data/processed/saol14-gamewords.txt"),
    Path("saol14-gamewords.txt"),
    Path("data/saol14-gamewords.txt"),
    Path("reports/saol14-gamewords.txt"),
)

VERIFIED = "verified"
STALE_VALIDATION = "stale_validation"
NOT_APPLICABLE = "not_applicable"


def resolve_gamewords_path(explicit: Path | None = None, *, root: Path = Path(".")) -> Path:
    """Resolve the final gamewords artifact without silently guessing a missing path."""
    if explicit is not None:
        if explicit.is_file():
            return explicit
        raise FileNotFoundError(f"Angiven gamewords-fil finns inte: {explicit}")

    for candidate in GAMEWORD_CANDIDATES:
        path = root / candidate
        if path.is_file():
            return path

    matches = sorted(
        (path for path in root.rglob(GAMEWORD_BASENAME) if path.is_file()),
        key=lambda path: (len(path.parts), str(path)),
    )
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        listed = "\n  ".join(str(path) for path in matches)
        raise FileNotFoundError(
            "Flera saol14-gamewords.txt hittades; ange rätt fil med --gamewords:\n  " + listed
        )

    searched = "\n  ".join(str(root / candidate) for candidate in GAMEWORD_CANDIDATES)
    raise FileNotFoundError(
        "Hittade ingen saol14-gamewords.txt. Kontrollerade:\n  "
        + searched
        + "\nSökvägen kan anges med --gamewords PATH. "
        + "Kör annars: find . -name 'saol14-gamewords.txt' -print"
    )


def read_jsonl(path: Path) -> list[dict[str, Any]]:
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


def read_gamewords(path: Path) -> set[str]:
    return {
        line.strip().casefold()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def audit_row(row: dict[str, Any], gamewords: set[str]) -> dict[str, Any]:
    classification = str(row.get("mismatch_classification") or UNCLASSIFIED)
    if classification == UNCLASSIFIED:
        return {
            **row,
            "classification_audit": NOT_APPLICABLE,
            "classification_audit_reasons": [],
            "forms_missing_from_gamewords": [],
        }

    reasons: list[str] = []
    upos = str(row.get("upos") or "").upper()
    generator = str(row.get("generator") or "")
    if upos in {"NOUN", "ADJ"} and generator != "canonical_artifact":
        reasons.append(f"non_artifact_generator:{generator or '(missing)'}")

    claimed_saol_only = {
        str(form).casefold()
        for form in row.get("extra_from_saol", ())
        if str(form)
    }
    missing_from_gamewords = sorted(claimed_saol_only - gamewords)
    if missing_from_gamewords:
        reasons.append("claimed_saol_forms_absent_from_gamewords")

    return {
        **row,
        "classification_audit": STALE_VALIDATION if reasons else VERIFIED,
        "classification_audit_reasons": reasons,
        "forms_missing_from_gamewords": missing_from_gamewords,
    }


def audit_rows(rows: Iterable[dict[str, Any]], gamewords: set[str]) -> list[dict[str, Any]]:
    return [audit_row(row, gamewords) for row in rows]


def build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    audit_counts = Counter(str(row["classification_audit"]) for row in rows)
    stale_by_class = Counter(
        str(row.get("mismatch_classification") or "")
        for row in rows
        if row["classification_audit"] == STALE_VALIDATION
    )
    verified_by_class = Counter(
        str(row.get("mismatch_classification") or "")
        for row in rows
        if row["classification_audit"] == VERIFIED
    )
    return {
        "rows": len(rows),
        "audit_counts": dict(sorted(audit_counts.items())),
        "verified_by_classification": dict(sorted(verified_by_class.items())),
        "stale_by_classification": dict(sorted(stale_by_class.items())),
        "stale_rows": [
            {
                "lemma": str(row.get("lemma") or ""),
                "homonym_number": str(row.get("homonym_number") or ""),
                "upos": str(row.get("upos") or ""),
                "notation": str(row.get("notation") or ""),
                "classification": str(row.get("mismatch_classification") or ""),
                "generator": str(row.get("generator") or ""),
                "reasons": list(row.get("classification_audit_reasons") or ()),
                "forms_missing_from_gamewords": list(row.get("forms_missing_from_gamewords") or ()),
            }
            for row in rows
            if row["classification_audit"] == STALE_VALIDATION
        ],
    }


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def render_text(summary: dict[str, Any]) -> str:
    counts = summary["audit_counts"]
    lines = [
        f"Reviderade mismatchposter: {summary['rows']}",
        f"Verifierade klassningar: {counts.get(VERIFIED, 0)}",
        f"Föråldrade/ogiltiga klassningar: {counts.get(STALE_VALIDATION, 0)}",
        f"Oklassificerade (ej tillämpligt): {counts.get(NOT_APPLICABLE, 0)}",
        "",
        "Verifierade per klass:",
    ]
    if not summary["verified_by_classification"]:
        lines.append("  (inga)")
    else:
        for name, count in summary["verified_by_classification"].items():
            lines.append(f"{count:5}  {name}")

    lines.extend(["", "Föråldrade per klass:"])
    if not summary["stale_by_classification"]:
        lines.append("  (inga)")
    else:
        for name, count in summary["stale_by_classification"].items():
            lines.append(f"{count:5}  {name}")

    stale_rows = summary["stale_rows"]
    lines.extend(["", f"Föråldrade poster ({len(stale_rows)}):"])
    if not stale_rows:
        lines.append("  (inga)")
    for row in stale_rows[:100]:
        reasons = ", ".join(row["reasons"]) or "-"
        missing = ", ".join(row["forms_missing_from_gamewords"]) or "-"
        lines.append(
            f"  {row['lemma']} ({row['homonym_number']}) | {row['upos']} | "
            f"{row['classification']} | generator={row['generator']} | "
            f"saknas i gamewords={missing} | skäl={reasons}"
        )
    return "\n".join(lines) + "\n"


def audit_file(
    classifications_path: Path = DEFAULT_CLASSIFICATIONS,
    *,
    gamewords_path: Path | None = None,
    jsonl_path: Path = DEFAULT_JSONL,
    summary_path: Path = DEFAULT_SUMMARY,
    text_path: Path = DEFAULT_TEXT,
) -> dict[str, Any]:
    resolved_gamewords = resolve_gamewords_path(gamewords_path)
    rows = audit_rows(read_jsonl(classifications_path), read_gamewords(resolved_gamewords))
    write_jsonl(jsonl_path, rows)
    summary = build_summary(rows)
    summary.update(
        {
            "classifications": str(classifications_path),
            "gamewords": str(resolved_gamewords),
            "jsonl": str(jsonl_path),
            "summary": str(summary_path),
            "text": str(text_path),
        }
    )
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    text_path.parent.mkdir(parents=True, exist_ok=True)
    text_path.write_text(render_text(summary), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Revidera mismatchklassningar mot kanonisk artefaktkälla och slutlig gamewords-lista"
    )
    parser.add_argument("classifications", nargs="?", type=Path, default=DEFAULT_CLASSIFICATIONS)
    parser.add_argument("--gamewords", type=Path)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    args = parser.parse_args()
    summary = audit_file(
        args.classifications,
        gamewords_path=args.gamewords,
        jsonl_path=args.jsonl,
        summary_path=args.summary,
        text_path=args.text,
    )
    print(f"Reviderade mismatchposter: {summary['rows']}")
    for name, count in summary["audit_counts"].items():
        print(f"{name}: {count}")
    print(f"Gamewords: {summary['gamewords']}")
    print(f"Rapport: {summary['text']}")


if __name__ == "__main__":
    main()
