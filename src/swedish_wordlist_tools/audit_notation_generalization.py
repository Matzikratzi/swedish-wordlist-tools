from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any

DEFAULT_ROOT = Path("src/swedish_wordlist_tools")
DEFAULT_TEXT = Path("reports/saol14-notation-generalization-audit.txt")
DEFAULT_JSON = Path("reports/saol14-notation-generalization-audit.json")

# Focus on code that turns SAOL `text` notation into forms. Analysis/report
# modules are deliberately excluded: they may use regex freely without adding
# parser complexity to production.
TARGETS = (
    "saol_notation.py",
    "noun_notation_interpreter.py",
    "adjective_variant_interpreter.py",
    "verb_notation_interpreter.py",
    "generate_pronoun_forms.py",
    "generate_numeral_forms.py",
    "generate_adverb_forms.py",
)


def _source_segment(source: str, node: ast.AST) -> str:
    return (ast.get_source_segment(source, node) or "").strip()


def audit_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"file": path.name, "missing": True, "regex_calls": [], "text_conditionals": [], "operation_calls": 0}
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    regex_calls: list[dict[str, Any]] = []
    text_conditionals: list[dict[str, Any]] = []
    operation_calls = 0

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = ""
            if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                name = f"{node.func.value.id}.{node.func.attr}"
            elif isinstance(node.func, ast.Name):
                name = node.func.id
            if name in {"re.match", "re.search", "re.fullmatch", "re.findall", "re.finditer", "re.compile"}:
                regex_calls.append({"line": getattr(node, "lineno", 0), "code": _source_segment(source, node)})
            if name in {"parse_form_operation", "apply_form_operation"}:
                operation_calls += 1
        elif isinstance(node, ast.If):
            code = _source_segment(source, node.test)
            if "text" in code and any(token in code for token in ("==", " in ", "startswith", "endswith")):
                text_conditionals.append({"line": getattr(node, "lineno", 0), "code": code})

    return {
        "file": path.name,
        "missing": False,
        "regex_calls": regex_calls,
        "text_conditionals": text_conditionals,
        "operation_calls": operation_calls,
    }


def analyze(root: Path = DEFAULT_ROOT) -> dict[str, Any]:
    files = [audit_file(root / name) for name in TARGETS]
    existing = [row for row in files if not row["missing"]]
    return {
        "files": files,
        "existing_files": len(existing),
        "missing_files": sum(1 for row in files if row["missing"]),
        "regex_calls": sum(len(row["regex_calls"]) for row in existing),
        "text_conditionals": sum(len(row["text_conditionals"]) for row in existing),
        "operation_calls": sum(row["operation_calls"] for row in existing),
    }


def render_text(report: dict[str, Any]) -> str:
    lines = [
        "SAOL-notation: generaliseringsaudit",
        "",
        f"Produktionsmoduler funna: {report['existing_files']}",
        f"Regex-anrop i dessa: {report['regex_calls']}",
        f"Direkta textvillkor: {report['text_conditionals']}",
        f"Anrop till generella formoperationer: {report['operation_calls']}",
        "",
        "Per modul:",
    ]
    for row in report["files"]:
        if row["missing"]:
            lines.append(f"\n{row['file']}: saknas")
            continue
        lines.append(
            f"\n{row['file']}: regex={len(row['regex_calls'])}, "
            f"textvillkor={len(row['text_conditionals'])}, operationer={row['operation_calls']}"
        )
        for item in row["regex_calls"]:
            lines.append(f"  R{item['line']}: {item['code']}")
        for item in row["text_conditionals"]:
            lines.append(f"  T{item['line']}: {item['code']}")
    lines.extend([
        "",
        "Tolkning:",
        "- Regex i saol_notation.py är normalt gemensam token-/operationssyntax och är inte i sig teknisk skuld.",
        "- Regex/textvillkor i ordklassspecifika generatorer är kandidater för gemensamma LABEL/FORM/OPERATION-token.",
        "- En refaktorering är värd att göra om samma label-/formmönster återkommer i flera ordklassmoduler; annars bör regeln få stanna lokal.",
    ])
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit remaining class-specific SAOL notation parsing")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--text", type=Path, default=DEFAULT_TEXT)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()
    report = analyze(args.root)
    args.text.parent.mkdir(parents=True, exist_ok=True)
    args.text.write_text(render_text(report), encoding="utf-8")
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Produktionsmoduler funna: {report['existing_files']}")
    print(f"Regex-anrop: {report['regex_calls']}")
    print(f"Direkta textvillkor: {report['text_conditionals']}")
    print(f"Generella operationsanrop: {report['operation_calls']}")
    print(f"Text: {args.text}")


if __name__ == "__main__":
    main()
