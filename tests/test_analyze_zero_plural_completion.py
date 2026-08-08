import unittest

from swedish_wordlist_tools.analyze_zero_plural_completion import render_text


class AnalyzeZeroPluralCompletionTests(unittest.TestCase):
    def test_render_mentions_derived_definite_plural(self):
        summary = {
            "records": 1,
            "rows_with_derived_definite_plural": 1,
            "form_kind_counts": {"derived_definite_plural": 1},
            "source_stage_counts": {"noun_completion": 1},
            "rows": [
                {
                    "lemma": "hertz",
                    "record_id": "1",
                    "homonym_number": "1",
                    "extra_from_saol": ["hertzna"],
                    "missing_from_saol": ["hertzen"],
                    "artifact_forms": [
                        {
                            "written_form": "hertzna",
                            "msd": "pl def nom",
                            "kind": "derived_definite_plural",
                            "source_stage": "noun_completion",
                        }
                    ],
                }
            ],
        }
        text = render_text(summary)
        self.assertIn("derived_definite_plural", text)
        self.assertIn("hertz", text)
        self.assertIn("noun_completion", text)


if __name__ == "__main__":
    unittest.main()
