from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .artifact_paths import SAOL14_ADJECTIVE_FORMS, SAOL14_NOUN_FORMS

DEFAULT_NOUN_FORMS = SAOL14_NOUN_FORMS
DEFAULT_ADJECTIVE_FORMS = SAOL14_ADJECTIVE_FORMS

ArtifactKey = tuple[str, str, str]


def record_key(record: dict[str, Any]) -> ArtifactKey:
    return (
        str(record.get("id") or record.get("subnr") or record.get("urspr_lopnr") or ""),
        str(record.get("homonr") or ""),
        str(record.get("normaliserat_ord") or "").casefold(),
    )


def artifact_row_key(row: dict[str, Any]) -> ArtifactKey:
    return (
        str(row.get("record_id") or ""),
        str(row.get("homonym_number") or ""),
        str(row.get("lemma") or "").casefold(),
    )


def artifact_forms(row: dict[str, Any]) -> set[str]:
    return {
        str(form.get("written_form") or "")
        for form in row.get("forms", ())
        if str(form.get("written_form") or "")
    }


def artifact_variant_lemmas(row: dict[str, Any]) -> tuple[str, ...]:
    values = [str(value or "").strip() for value in row.get("variant_lemmas", ())]
    values = [value for value in values if value]
    if values:
        return tuple(values)
    lemma = str(row.get("lemma") or "").strip()
    return (lemma,) if lemma else ()


def read_artifact(path: Path) -> dict[ArtifactKey, set[str]]:
    result: dict[ArtifactKey, set[str]] = {}
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"Ogiltig JSON på rad {number} i {path}") from error
            key = artifact_row_key(row)
            forms = artifact_forms(row)
            previous = result.get(key)
            if previous is not None and previous != forms:
                raise ValueError(f"Motstridiga artefaktrader för {key} i {path}")
            result[key] = forms
    return result


def read_artifact_variant_lemmas(path: Path) -> dict[ArtifactKey, tuple[str, ...]]:
    result: dict[ArtifactKey, tuple[str, ...]] = {}
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"Ogiltig JSON på rad {number} i {path}") from error
            key = artifact_row_key(row)
            lemmas = artifact_variant_lemmas(row)
            previous = result.get(key)
            if previous is not None and previous != lemmas:
                raise ValueError(f"Motstridiga variantlemma för {key} i {path}")
            result[key] = lemmas
    return result


def load_word_class_artifacts(
    *,
    noun_path: Path = DEFAULT_NOUN_FORMS,
    adjective_path: Path = DEFAULT_ADJECTIVE_FORMS,
) -> dict[str, dict[ArtifactKey, set[str]]]:
    return {
        "NOUN": read_artifact(noun_path),
        "ADJ": read_artifact(adjective_path),
    }


def forms_from_artifacts(
    record: dict[str, Any],
    artifacts: dict[str, dict[ArtifactKey, set[str]]],
) -> set[str] | None:
    upos = str(record.get("upos") or "").upper()
    index = artifacts.get(upos)
    if index is None:
        return None
    return index.get(record_key(record))


def variant_lemmas_from_artifact(
    record: dict[str, Any],
    variant_lemmas: dict[ArtifactKey, tuple[str, ...]],
) -> tuple[str, ...] | None:
    return variant_lemmas.get(record_key(record))
