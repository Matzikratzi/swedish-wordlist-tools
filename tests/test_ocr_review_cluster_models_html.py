from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from swedish_wordlist_tools.ocr_glyph_matcher import Match
from swedish_wordlist_tools.ocr_review_cluster_models_html import (
    REVIEW_FORMAT,
    cluster_model_fingerprint,
    load_reviews,
    render_page,
    review_statuses,
    save_review,
)


def _match(label="fr", *, pixels=None, style="roman", x=10, baseline=20):
    pixels = pixels or frozenset({(10, 18), (11, 18), (10, 19), (12, 20)})
    return Match(
        label=label,
        style=style,
        x=x,
        baseline=baseline,
        pixels=frozenset(pixels),
        model_pixels=len(pixels),
        sources=1,
    )


def _model(fingerprint="abc", status_label="fr"):
    return {
        "fingerprint": fingerprint,
        "label": status_label,
        "style": "roman",
        "sources": 1,
        "model_pixels": [[0, -2], [1, -2], [0, -1], [2, 0]],
        "model_bbox": [0, -2, 2, 0],
        "uses": [
            {
                "page": 1,
                "column": 0,
                "row": 20,
                "text": "abbé s. ~n ~er ¤ fransk",
                "image": "data:image/png;base64,AA==",
                "crop_width": 191,
                "crop_height": 17,
                "bbox": [10, 18, 12, 20],
                "x": 10,
                "baseline": 20,
                "pixels": [[10, 18], [11, 18], [10, 19], [12, 20]],
            }
        ],
    }


class ClusterReviewTests(unittest.TestCase):
    def test_fingerprint_is_raster_specific_not_only_label(self):
        first = _match()
        second = _match(pixels=frozenset({(10, 18), (11, 18), (12, 18), (12, 20)}))
        same_shape_shifted = _match(
            x=30,
            baseline=40,
            pixels=frozenset({(30, 38), (31, 38), (30, 39), (32, 40)}),
        )
        self.assertNotEqual(cluster_model_fingerprint(first), cluster_model_fingerprint(second))
        self.assertEqual(cluster_model_fingerprint(first), cluster_model_fingerprint(same_shape_shifted))

    def test_review_round_trip_persists_approved_and_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "review.json"
            first = _model("first", "fr")
            second = _model("second", "st")
            save_review(path, first, "approved")
            save_review(path, second, "rejected")

            payload = load_reviews(path)
            self.assertEqual(payload["format"], REVIEW_FORMAT)
            self.assertEqual(review_statuses(path), {"first": "approved", "second": "rejected"})

    def test_pending_view_hides_approved_but_keeps_rejected(self):
        approved = _model("approved", "fr")
        rejected = _model("rejected", "st")
        document = render_page(
            [approved, rejected],
            {"approved": "approved", "rejected": "rejected"},
            0,
            0,
            pending_only=True,
        )
        self.assertIn("<code>st</code>", document)
        self.assertIn("status-rejected", document)
        self.assertNotIn("<code>fr</code>", document)

    def test_all_approved_has_done_page(self):
        document = render_page(
            [_model("approved", "fr")],
            {"approved": "approved"},
            0,
            0,
            pending_only=True,
        )
        self.assertIn("Alla klustermodeller är godkända", document)


if __name__ == "__main__":
    unittest.main()
