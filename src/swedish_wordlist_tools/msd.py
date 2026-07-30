from __future__ import annotations

import re
from dataclasses import dataclass


_PARADIGM_RE = re.compile(r"^[1-9][0-9]*:[1-9][0-9]*-[1-9][0-9]*$")


@dataclass(frozen=True, slots=True)
class Msd:
    """Parsed SALDO MSD value with lossless round-trip formatting.

    SALDO sometimes appends a paradigm position such as ``1:2-3`` to the
    grammatical tags. The original string is preserved verbatim while the
    grammatical portion and optional paradigm position are exposed separately.
    """

    raw: str
    tags: tuple[str, ...]
    paradigm: str | None = None

    @classmethod
    def parse(cls, value: str | Msd) -> Msd:
        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            raise TypeError(f"MSD must be str or Msd, got {type(value).__name__}")

        raw = value
        parts = value.split()
        paradigm = parts[-1] if parts and _PARADIGM_RE.fullmatch(parts[-1]) else None
        tags = tuple(parts[:-1] if paradigm is not None else parts)
        return cls(raw=raw, tags=tags, paradigm=paradigm)

    @property
    def has_paradigm(self) -> bool:
        return self.paradigm is not None

    @property
    def grammar(self) -> str:
        return " ".join(self.tags)

    def casefold(self) -> str:
        """Compatibility helper for code that previously stored raw strings."""
        return self.raw.casefold()

    def __bool__(self) -> bool:
        return bool(self.raw)

    def __str__(self) -> str:
        return self.raw


def parse_msd(value: str | Msd) -> Msd:
    """Parse an MSD value while accepting already parsed instances."""
    return Msd.parse(value)
