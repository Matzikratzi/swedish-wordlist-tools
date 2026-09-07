from __future__ import annotations

"""Profile the current OCR benchmark without changing OCR semantics.

This wrapper runs the existing single-downshift benchmark under ``cProfile`` and
prints a compact machine-greppable report afterwards.  It deliberately does not
instrument or reorder anything inside the matcher, so the profile describes the
same algorithm that is used by the underlying benchmark.
"""

import cProfile
import pstats

from . import ocr_single_downshift_safe_islands_benchmark as benchmark


def _label(func: tuple[str, int, str]) -> str:
    filename, line, name = func
    return f"{filename}:{line}:{name}"


def _print_profile(profile: cProfile.Profile, *, top: int = 40) -> None:
    stats = pstats.Stats(profile)
    rows = []
    for func, values in stats.stats.items():
        cc, nc, self_time, cumulative_time, _callers = values
        rows.append(
            (
                float(self_time),
                float(cumulative_time),
                int(cc),
                int(nc),
                _label(func),
            )
        )

    total_self = sum(row[0] for row in rows)
    primitive_calls = sum(row[2] for row in rows)
    total_calls = sum(row[3] for row in rows)
    print(
        "cprofile-summary: "
        f"functions={len(rows)} total_self={total_self:.6f}s "
        f"primitive_calls={primitive_calls} total_calls={total_calls}",
        flush=True,
    )

    print(f"cprofile-top-self: top={top}", flush=True)
    for rank, (self_time, cumulative_time, cc, nc, label) in enumerate(
        sorted(rows, key=lambda row: (-row[0], -row[1], row[4]))[:top],
        start=1,
    ):
        pct = 100.0 * self_time / total_self if total_self else 0.0
        print(
            "cprofile-self: "
            f"rank={rank} self={self_time:.6f}s self_pct={pct:.1f} "
            f"cum={cumulative_time:.6f}s cc={cc} nc={nc} func={label!r}",
            flush=True,
        )

    print(f"cprofile-top-cumulative: top={top}", flush=True)
    for rank, (self_time, cumulative_time, cc, nc, label) in enumerate(
        sorted(rows, key=lambda row: (-row[1], -row[0], row[4]))[:top],
        start=1,
    ):
        print(
            "cprofile-cumulative: "
            f"rank={rank} cum={cumulative_time:.6f}s self={self_time:.6f}s "
            f"cc={cc} nc={nc} func={label!r}",
            flush=True,
        )


def main() -> int:
    profile = cProfile.Profile()
    profile.enable()
    try:
        result = benchmark.main()
    finally:
        profile.disable()
        _print_profile(profile)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
