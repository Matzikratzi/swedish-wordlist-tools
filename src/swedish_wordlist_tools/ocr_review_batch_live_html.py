from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path

from . import ocr_review_batch_defects_html as batch
from .ocr_batch_progress_cache import BatchProgressStore, DEFAULT_CACHE_PATH
from .ocr_review_batch_prefetch import BatchPrefetcher


class InteractivePriorityGate:
    """Let interactive review pre-empt background row analysis.

    Background analysis is allowed only while no interactive row load/edit is
    active or waiting. Interactive work may run concurrently with other
    interactive work, preserving the five-row editor's parallel row loading.
    A short grace period after an edit keeps the background worker from jumping
    in between the POST and the browser's redirected GET.
    """

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._interactive_active = 0
        self._interactive_waiting = 0
        self._background_active = False
        self._background_not_before = 0.0

    def interactive_call(self, fn, *args, grace_seconds: float = 0.0, **kwargs):
        with self._condition:
            self._interactive_waiting += 1
            try:
                while self._background_active:
                    self._condition.wait()
                self._interactive_active += 1
            finally:
                self._interactive_waiting -= 1
        try:
            return fn(*args, **kwargs)
        finally:
            with self._condition:
                self._interactive_active -= 1
                if grace_seconds > 0:
                    self._background_not_before = max(
                        self._background_not_before,
                        time.monotonic() + float(grace_seconds),
                    )
                self._condition.notify_all()

    def background_call(self, fn, *args, **kwargs):
        with self._condition:
            while True:
                now = time.monotonic()
                delay = self._background_not_before - now
                blocked = (
                    self._background_active
                    or self._interactive_active > 0
                    or self._interactive_waiting > 0
                    or delay > 0
                )
                if not blocked:
                    self._background_active = True
                    break
                self._condition.wait(timeout=max(0.001, delay) if delay > 0 else None)
        try:
            return fn(*args, **kwargs)
        finally:
            with self._condition:
                self._background_active = False
                self._condition.notify_all()


def _live_args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("jsonl", type=Path)
    ap.add_argument("--pages", required=True)
    ap.add_argument("--threshold", type=int, default=210)
    ap.add_argument("--facit", type=Path, default=Path("glyphs/saol14-manual-glyph-facit.json"))
    ap.add_argument("--progress-cache", type=Path, default=DEFAULT_CACHE_PATH)
    args, _unknown = ap.parse_known_args(argv[1:])
    return args


def main() -> int:
    live = _live_args(sys.argv)
    pages = batch.parse_pages(live.pages)
    original_launch_editor = batch.launch_editor

    def launch_with_prefetch(
        jsonl: Path,
        *,
        page: int,
        position: tuple[int, int],
        threshold: int,
        facit: Path,
        host: str,
        port: int,
        no_browser: bool,
    ) -> int:
        later_pages = [candidate for candidate in pages if candidate > page]
        prefetcher = BatchPrefetcher(
            jsonl=jsonl,
            pages=later_pages,
            threshold=threshold,
            facit=facit,
            progress_store=BatchProgressStore(live.progress_cache),
        )
        gate = InteractivePriorityGate()

        original_audit_loader = batch._load_review_state_for_audit
        original_editor_loader = batch.boundary.fast.load_review_state_fast
        original_apply_edit = batch.boundary.fast.legacy.apply_edit

        def priority_audit_loader(context, row_position, models):
            if threading.current_thread().name == "ocr-batch-prefetch":
                return gate.background_call(original_audit_loader, context, row_position, models)
            return original_audit_loader(context, row_position, models)

        def priority_editor_loader(context, row_position, models):
            if threading.current_thread().name == "ocr-batch-prefetch":
                return original_editor_loader(context, row_position, models)
            return gate.interactive_call(
                original_editor_loader,
                context,
                row_position,
                models,
                grace_seconds=0.10,
            )

        def priority_apply_edit(state, edit_facit, form):
            # Keep background work away long enough for the POST to finish and
            # the browser to start the redirected GET that redraws the row.
            return gate.interactive_call(
                original_apply_edit,
                state,
                edit_facit,
                form,
                grace_seconds=1.5,
            )

        batch._load_review_state_for_audit = priority_audit_loader
        batch.boundary.fast.load_review_state_fast = priority_editor_loader
        batch.boundary.fast.legacy.apply_edit = priority_apply_edit

        prefetcher.start()
        try:
            return original_launch_editor(
                jsonl,
                page=page,
                position=position,
                threshold=threshold,
                facit=facit,
                host=host,
                port=port,
                no_browser=no_browser,
            )
        finally:
            prefetcher.stop()
            batch._load_review_state_for_audit = original_audit_loader
            batch.boundary.fast.load_review_state_fast = original_editor_loader
            batch.boundary.fast.legacy.apply_edit = original_apply_edit

    batch.launch_editor = launch_with_prefetch
    try:
        return batch.main()
    finally:
        batch.launch_editor = original_launch_editor


if __name__ == "__main__":
    raise SystemExit(main())
