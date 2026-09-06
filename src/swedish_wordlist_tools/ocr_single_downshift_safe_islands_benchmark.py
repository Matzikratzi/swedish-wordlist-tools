from __future__ import annotations

"""Compatibility layer for the single-downshift benchmark stage.

The deterministic one-time B -> B+1 rule is now installed in the shared row
parser used by editor, scanner and benchmark.  This stage deliberately does not
monkeypatch a benchmark-only analyser anymore; it only preserves the historical
benchmark chain and delegates to the next stage.
"""

from . import ocr_monotonic_proof_boundary_benchmark as monotonic


def main() -> int:
    return monotonic.main()


if __name__ == "__main__":
    raise SystemExit(main())
