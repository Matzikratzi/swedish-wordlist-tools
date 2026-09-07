from __future__ import annotations

from . import ocr_compare_page_text_prefix as base


def main() -> int:
    """Compatibility alias; grouped exact matching is now the default comparator path."""
    return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
