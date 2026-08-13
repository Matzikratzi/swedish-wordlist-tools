from __future__ import annotations

import unicodedata

from . import analyze_saol_bars as base

MAX_TRUNCATED_SUFFIX = 6


def accentless_word(value: str) -> str:
    """Return the compact comparison form without combining accents."""
    decomposed = unicodedata.normalize("NFKD", base.compact_word(value))
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def classify_candidate(lemma: str, value: str) -> tuple[str, list[str]]:
    """Classify explicit SAOL bars, including safe OCR truncation recovery.

    A candidate is accepted when it reconstructs the lemma exactly, when the
    only difference is an accent, or when the compact candidate is a prefix of
    the lemma and at most six final letters have been truncated in the source.
    """
    parts = base.split_bar_candidate(value)
    if len(parts) < 2:
        return "invalid_saol_bar", parts

    candidate = base.compact_word("".join(parts))
    target = base.compact_lemma(lemma)

    if candidate == target:
        return "saol_bar_matches_lemma", parts

    if accentless_word(candidate) == accentless_word(target):
        return "saol_bar_matches_lemma", parts

    missing = len(target) - len(candidate)
    if 1 <= missing <= MAX_TRUNCATED_SUFFIX and target.startswith(candidate):
        return "saol_bar_matches_truncated_lemma", parts

    return "saol_bar_does_not_match_lemma", parts


def main() -> None:
    # Keep the established analysis/output pipeline, but replace its candidate
    # classifier for this run with the stricter recovery-aware implementation.
    base.classify_candidate = classify_candidate
    original_analyse_rows = base.analyse_rows

    def analyse_rows(*args, **kwargs):
        rows, _counts = original_analyse_rows(*args, **kwargs)
        counts: dict[str, int] = {}
        for row in rows:
            candidates = row.get("saol_bar_candidates", [])
            matching = [
                candidate
                for candidate in candidates
                if candidate.get("reason") in {
                    "saol_bar_matches_lemma",
                    "saol_bar_matches_truncated_lemma",
                }
            ]
            row["saol_bar_splits"] = matching
            if len(matching) == 1:
                reason = "unique_saol_bar_split"
            elif len(matching) > 1:
                reason = "multiple_saol_bar_splits"
            elif candidates:
                reason = "saol_bar_does_not_match_lemma"
            else:
                reason = "no_saol_bar"
            row["saol_bar_reason"] = reason
            counts[reason] = counts.get(reason, 0) + 1
        return rows, dict(sorted(counts.items()))

    base.analyse_rows = analyse_rows
    base.main()


if __name__ == "__main__":
    main()
