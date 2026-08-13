from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .artifact_paths import SAOL14_ADJECTIVE_FORMS, SAOL14_NOUN_FORMS
from .saol_surface import clean_saol_word

DEFAULT_NOUN_FORMS = SAOL14_NOUN_FORMS
DEFAULT_ADJECTIVE_FORMS = SAOL14_ADJECTIVE_FORMS

ArtifactKey = tuple[str, str, str]
VariantParadigms = dict[str, set[str]]


def record_key(record: dict[str, Any]) -> ArtifactKey:
    return (
        str(record.get("id") or record.get("subnr") or record.get("urspr_lopnr") or ""),
        str(record.get("homonr") or ""),
        str(record.get("normaliserat_ord") or "").casefold(),
    )


def record_keys(record: dict[str, Any]) -> tuple[ArtifactKey, ...]:
    """Return lookup keys from most specific written form to normalized lemma.

    SAOL faksimil can have several source rows with the same record id, homonym
    number and ``normaliserat_ord`` but different explicit ``ord`` forms, e.g.
    ``disko``/``disco``.  A rebased artifact is keyed by its actual written
    lemma, so try cleaned ``ord`` first and use ``normaliserat_ord`` only as a
    fallback for ordinary rows and complex variants such as ``ankare``/``ankar``.
    """

    base = record_key(record)
    written = clean_saol_word(record.get("ord"))
    keys: list[ArtifactKey] = []
    if written:
        keys.append((base[0], base[1], written.casefold()))
    keys.append(base)
    return tuple(dict.fromkeys(keys))


def artifact_row_key(row: dict[str, Any]) -> ArtifactKey:
    return (
        str(row.get("record_id") or ""),
        str(row.get("homonym_number") or ""),
        str(row.get("lemma") or "").casefold(),
    )


def artifact_row_keys(row: dict[str, Any]) -> tuple[ArtifactKey, ...]:
    """Return every homonym alias represented by one materialized artifact row.

    Do not alias a rebased variant back to ``source_normaliserat_ord`` here.
    Multiple written variants can legitimately share that source identity while
    carrying different paradigms.  Raw-record lookup resolves the explicit
    cleaned ``ord`` first via :func:`record_keys`.
    """

    record_id = str(row.get("record_id") or "")
    lemma = str(row.get("lemma") or "").casefold()
    aliases = [str(value or "") for value in row.get("source_homonym_numbers", ()) if str(value or "")]
    if not aliases:
        aliases = [str(row.get("homonym_number") or "")]
    return tuple(dict.fromkeys((record_id, homonym, lemma) for homonym in aliases))


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


def artifact_variant_paradigms(row: dict[str, Any]) -> VariantParadigms:
    result: VariantParadigms = {}
    for paradigm in row.get("variant_paradigms", ()):
        lemma = str(paradigm.get("lemma") or "").strip()
        if not lemma:
            continue
        result[lemma] = {
            str(form.get("written_form") or "")
            for form in paradigm.get("forms", ())
            if str(form.get("written_form") or "")
        }
    if result:
        return result
    lemma = str(row.get("lemma") or "").strip()
    return {lemma: artifact_forms(row)} if lemma else {}


def _read_rows(path: Path) -> list[dict[str, Any]]:
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


def read_artifact_rows(path: Path) -> list[dict[str, Any]]:
    """Read materialized artifact rows without regenerating any forms."""

    return _read_rows(path)


def _merge_value(previous: Any, value: Any) -> Any:
    if isinstance(previous, set) and isinstance(value, set):
        return previous | value
    if isinstance(previous, tuple) and isinstance(value, tuple):
        return tuple(dict.fromkeys((*previous, *value)))
    if isinstance(previous, dict) and isinstance(value, dict):
        merged = {key: set(forms) for key, forms in previous.items()}
        for lemma, forms in value.items():
            merged.setdefault(lemma, set()).update(forms)
        return merged
    return value if previous == value else None


def _store_aliases(result: dict[ArtifactKey, Any], row: dict[str, Any], value: Any, path: Path, label: str) -> None:
    for key in artifact_row_keys(row):
        previous = result.get(key)
        if previous is None:
            result[key] = value
            continue
        merged = _merge_value(previous, value)
        if merged is None:
            raise ValueError(f"Motstridiga {label} för {key} i {path}")
        result[key] = merged


def read_artifact(path: Path) -> dict[ArtifactKey, set[str]]:
    result: dict[ArtifactKey, set[str]] = {}
    for row in _read_rows(path):
        _store_aliases(result, row, artifact_forms(row), path, "artefaktrader")
    return result


def read_artifact_variant_lemmas(path: Path) -> dict[ArtifactKey, tuple[str, ...]]:
    result: dict[ArtifactKey, tuple[str, ...]] = {}
    for row in _read_rows(path):
        _store_aliases(result, row, artifact_variant_lemmas(row), path, "variantlemma")
    return result


def read_artifact_variant_paradigms(path: Path) -> dict[ArtifactKey, VariantParadigms]:
    result: dict[ArtifactKey, VariantParadigms] = {}
    for row in _read_rows(path):
        _store_aliases(result, row, artifact_variant_paradigms(row), path, "variantparadigm")
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


def _lookup_record(record: dict[str, Any], index: dict[ArtifactKey, Any]) -> Any | None:
    for key in record_keys(record):
        value = index.get(key)
        if value is not None:
            return value
    return None


def forms_from_artifacts(
    record: dict[str, Any],
    artifacts: dict[str, dict[ArtifactKey, set[str]]],
) -> set[str] | None:
    upos = str(record.get("upos") or "").upper()
    index = artifacts.get(upos)
    if index is None:
        return None
    return _lookup_record(record, index)


def variant_lemmas_from_artifact(
    record: dict[str, Any],
    variant_lemmas: dict[ArtifactKey, tuple[str, ...]],
) -> tuple[str, ...] | None:
    return _lookup_record(record, variant_lemmas)


def variant_paradigms_from_artifact(
    record: dict[str, Any],
    variant_paradigms: dict[ArtifactKey, VariantParadigms],
) -> VariantParadigms | None:
    return _lookup_record(record, variant_paradigms)
