from __future__ import annotations

import re


_PARADIGM_RE = re.compile(r"^[1-9][0-9]*:[1-9][0-9]*-[1-9][0-9]*$")


class Msd(str):
    """SALDO MSD string with parsed grammatical and paradigm components.

    ``Msd`` is a ``str`` subclass so existing sorting, counters, JSON export and
    string comparisons remain compatible. The original value is therefore
    always preserved exactly while parsed views are available as properties.
    """

    def __new__(cls, value: str = "") -> Msd:
        if not isinstance(value, str):
            raise TypeError(f"MSD must be str or Msd, got {type(value).__name__}")
        return super().__new__(cls, value)

    @classmethod
    def parse(cls, value: str | Msd) -> Msd:
        if isinstance(value, cls):
            return value
        return cls(value)

    @property
    def raw(self) -> str:
        return str(self)

    @property
    def tags(self) -> tuple[str, ...]:
        parts = self.split()
        if parts and _PARADIGM_RE.fullmatch(parts[-1]):
            parts = parts[:-1]
        return tuple(parts)

    @property
    def paradigm(self) -> str | None:
        parts = self.split()
        if parts and _PARADIGM_RE.fullmatch(parts[-1]):
            return parts[-1]
        return None

    @property
    def has_paradigm(self) -> bool:
        return self.paradigm is not None

    @property
    def grammar(self) -> str:
        return " ".join(self.tags)


def parse_msd(value: str | Msd) -> Msd:
    """Parse an MSD value while accepting already parsed instances."""
    return Msd.parse(value)
