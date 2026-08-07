from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Canonical project-relative artifact paths. Keep these relative so existing CLI
# output and report metadata remain stable, but resolve them against PROJECT_ROOT
# whenever code needs an absolute filesystem path.
SAOL14_GAMEWORDS = Path("data/processed/saol14-gamewords.txt")
SAOL14_NOUN_FORMS = Path("reports/saol14-noun-forms.jsonl")
SAOL14_ADJECTIVE_FORMS = Path("reports/saol14-adjective-forms.jsonl")
SAOL14_VERB_FORMS = Path("data/processed/saol14-verb-forms.txt")
SALDO_FORMS = Path("reports/saldo-forms.jsonl")


def absolute_path(path: Path) -> Path:
    """Resolve a project artifact path against the repository root."""

    return path if path.is_absolute() else PROJECT_ROOT / path


def gamewords_path() -> Path:
    """Return the one official project-relative SAOL14 gameword path."""

    return SAOL14_GAMEWORDS


def absolute_gamewords_path() -> Path:
    """Return the absolute path to the official SAOL14 gameword artifact."""

    return absolute_path(SAOL14_GAMEWORDS)


def require_gamewords() -> Path:
    """Return the official gameword artifact or fail with its exact location."""

    path = absolute_gamewords_path()
    if not path.is_file():
        raise FileNotFoundError(
            "Den officiella SAOL14-spelordlistan saknas:\n"
            f"  {path}\n"
            "Officiell projektsökväg: data/processed/saol14-gamewords.txt"
        )
    return path


def main() -> None:
    path = absolute_gamewords_path()
    print("Officiell SAOL14-spelordlista:")
    print(f"  projekt: {SAOL14_GAMEWORDS}")
    print(f"  absolut: {path}")
    print(f"  finns: {'ja' if path.is_file() else 'nej'}")
    if path.is_file():
        count = sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
        print(f"  ord: {count}")


if __name__ == "__main__":
    main()
