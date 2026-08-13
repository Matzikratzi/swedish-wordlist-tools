from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from swedish_wordlist_tools.audit_notation_generalization import audit_file


class AuditNotationGeneralizationTests(unittest.TestCase):
    def test_counts_regex_text_conditions_and_generic_operations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.py"
            path.write_text(
                "import re\n"
                "def f(text, lemma):\n"
                "    xs = re.findall(r'\\w+', text)\n"
                "    if 'komp.' in text:\n"
                "        pass\n"
                "    op = parse_form_operation('+t')\n"
                "    return apply_form_operation(lemma, op)\n",
                encoding="utf-8",
            )
            row = audit_file(path)
        self.assertEqual(1, len(row["regex_calls"]))
        self.assertEqual(1, len(row["text_conditionals"]))
        self.assertEqual(2, row["operation_calls"])


if __name__ == "__main__":
    unittest.main()
