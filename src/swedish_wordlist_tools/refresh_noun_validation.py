from __future__ import annotations

import subprocess
import sys


MODULES = (
    "swedish_wordlist_tools.generate_noun_forms",
    "swedish_wordlist_tools.revalidate_direct_forms",
    "swedish_wordlist_tools.rebaseline_noun_validation",
    "swedish_wordlist_tools.analyze_remaining_noun_notations",
)


def main() -> None:
    """Rebuild NOUN forms before running every downstream validation report."""
    for module in MODULES:
        print(f"\n=== {module} ===", flush=True)
        subprocess.run([sys.executable, "-m", module], check=True)


if __name__ == "__main__":
    main()
