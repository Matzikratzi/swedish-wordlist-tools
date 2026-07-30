from __future__ import annotations

import re
import unicodedata
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from .msd import Msd, parse_msd


SALDO_POS_TO_UPOS = {
    "nn": "NOUN", "nnm": "NOUN", "nna": "NOUN", "pm": "PROPN",
    "vb": "VERB", "av": "ADJ", "ab": "ADV", "pn": "PRON",
    "dt": "DET", "pp": "ADP", "kn": "CCONJ", "sn": "SCONJ",
    "in": "INTJ", "rg": "NUM", "hp": "PRON", "ha": "ADV",
    "hd": "DET", "ie": "PART", "pc": "ADJ", "al": "X",
}


@dataclass(frozen=True)
class SaldoWordForm:
    """One SALDO WordForm with a losslessly parsed MSD value."""

    written_form: str
    msd: Msd = Msd(raw="", tags=())
    features: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class SaldoAnalysis:
    """One SALDO LexicalEntry with lemma and exact WordForm records."""

    entry_id: str
    upos: str
    lemmas: frozenset[str]
    word_forms: tuple[SaldoWordForm, ...]

    @property
    def forms(self) -> frozenset[str]:
        return frozenset(form.written_form for form in self.word_forms)

    def forms_for_msd(self, msd: str | Msd) -> tuple[str, ...]:
        wanted = parse_msd(msd).casefold()
        return tuple(
            form.written_form
            for form in self.word_forms
            if form.msd.casefold() == wanted
        )

    def as_legacy_dict(self) -> dict[str, object]:
        """Compatibility shape used by compare_sources during migration."""
        return {
            "id": self.entry_id,
            "upos": self.upos,
            "lemmas": set(self.lemmas),
            "forms": set(self.forms) | set(self.lemmas),
            "word_forms": [
                {
                    "writtenForm": form.written_form,
                    "msd": str(form.msd),
                    "features": dict(form.features),
                }
                for form in self.word_forms
            ],
        }


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _normalise(value: str) -> str:
    return unicodedata.normalize("NFC", value.strip())


def _key(value: str) -> str:
    return _normalise(value).casefold()


def _features(element: ET.Element) -> tuple[tuple[str, str], ...]:
    result: list[tuple[str, str]] = []
    for node in element.iter():
        if _local_name(node.tag).casefold() != "feat":
            continue
        name = node.attrib.get("att") or node.attrib.get("name") or ""
        value = node.attrib.get("val") or node.attrib.get("value") or node.text or ""
        name = _normalise(name)
        value = _normalise(value)
        if name and value:
            result.append((name, value))
    return tuple(result)


def _feature_values(element: ET.Element, name: str) -> list[str]:
    wanted = name.casefold()
    return [value for feature_name, value in _features(element) if feature_name.casefold() == wanted]


def _saldo_pos(element: ET.Element) -> str:
    candidates: list[str] = []
    for name in ("partOfSpeech", "pos", "wordClass"):
        candidates.extend(_feature_values(element, name))

    entry_id = element.attrib.get("id", "")
    match = re.search(r"\.\.([a-z]+)(?:\.|$)", entry_id.casefold())
    if match:
        candidates.append(match.group(1))

    known_upos = set(SALDO_POS_TO_UPOS.values())
    for candidate in candidates:
        compact = candidate.casefold().strip().rstrip(".")
        if compact.upper() in known_upos:
            return compact.upper()
        if compact in SALDO_POS_TO_UPOS:
            return SALDO_POS_TO_UPOS[compact]
    return ""


def _parse_word_forms(element: ET.Element) -> tuple[SaldoWordForm, ...]:
    result: list[SaldoWordForm] = []
    seen: set[tuple[str, str, tuple[tuple[str, str], ...]]] = set()
    for child in element:
        if _local_name(child.tag).casefold() != "wordform":
            continue
        features = _features(child)
        forms = [value for name, value in features if name.casefold() == "writtenform"]
        msd_values = [value for name, value in features if name.casefold() == "msd"]
        msd = parse_msd(msd_values[0] if msd_values else "")
        for written_form in forms:
            item = SaldoWordForm(written_form, msd, features)
            marker = (item.written_form, str(item.msd), item.features)
            if marker not in seen:
                seen.add(marker)
                result.append(item)
    return tuple(result)


def read_saldo_analyses(path: Path) -> dict[str, list[SaldoAnalysis]]:
    """Read SALDO grouped by lemma while preserving every WordForm and MSD."""
    entries: dict[str, list[SaldoAnalysis]] = defaultdict(list)
    for _, element in ET.iterparse(path, events=("end",)):
        if _local_name(element.tag).casefold() != "lexicalentry":
            continue

        lemmas: list[str] = []
        for child in element:
            if _local_name(child.tag).casefold() == "lemma":
                lemmas.extend(_feature_values(child, "writtenForm"))

        word_forms = _parse_word_forms(element)
        if not lemmas and word_forms:
            citation_forms = [form.written_form for form in word_forms if form.msd.casefold() == "ci"]
            lemmas = citation_forms or [word_forms[0].written_form]

        analysis = SaldoAnalysis(
            entry_id=element.attrib.get("id", ""),
            upos=_saldo_pos(element),
            lemmas=frozenset(lemmas),
            word_forms=word_forms,
        )
        for lemma in lemmas:
            entries[_key(lemma)].append(analysis)
        element.clear()
    return dict(entries)


def read_saldo_legacy(path: Path) -> dict[str, list[dict[str, object]]]:
    """Expose the old dictionary representation without discarding MSD data."""
    return {
        lemma: [analysis.as_legacy_dict() for analysis in analyses]
        for lemma, analyses in read_saldo_analyses(path).items()
    }
