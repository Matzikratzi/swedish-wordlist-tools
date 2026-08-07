from __future__ import annotations

from .revalidate_direct_forms_core import (
    ARTIFACT_WORD_CLASSES,
    canonical_validation_row,
    main,
    revalidate_direct_forms,
    select_article_variant_match_from_artifacts,
    select_direct_match_from_artifacts,
)

__all__ = [
    "ARTIFACT_WORD_CLASSES",
    "canonical_validation_row",
    "revalidate_direct_forms",
    "select_article_variant_match_from_artifacts",
    "select_direct_match_from_artifacts",
]


if __name__ == "__main__":
    main()
