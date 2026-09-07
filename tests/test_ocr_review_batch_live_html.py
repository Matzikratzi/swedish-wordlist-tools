from __future__ import annotations

import threading
import time
import unittest

from swedish_wordlist_tools.ocr_review_batch_live_html import InteractivePriorityGate


class InteractivePriorityGateTests(unittest.TestCase):
    def test_interactive_waiter_gets_priority_before_next_background_row(self) -> None:
        gate = InteractivePriorityGate()
        first_background_started = threading.Event()
        release_first_background = threading.Event()
        interactive_done = threading.Event()
        order: list[str] = []

        def first_background():
            order.append("background-1-start")
            first_background_started.set()
            release_first_background.wait(1.0)
            order.append("background-1-end")

        def interactive():
            first_background_started.wait(1.0)
            gate.interactive_call(lambda: order.append("interactive"))
            interactive_done.set()

        background_thread = threading.Thread(
            target=lambda: gate.background_call(first_background),
            name="ocr-batch-prefetch",
        )
        interactive_thread = threading.Thread(target=interactive, name="glyph-row_0")
        background_thread.start()
        interactive_thread.start()
        self.assertTrue(first_background_started.wait(1.0))
        time.sleep(0.02)
        release_first_background.set()
        background_thread.join(1.0)
        interactive_thread.join(1.0)

        self.assertTrue(interactive_done.is_set())
        self.assertEqual(order, ["background-1-start", "background-1-end", "interactive"])

    def test_multiple_interactive_calls_can_overlap(self) -> None:
        gate = InteractivePriorityGate()
        entered = 0
        peak = 0
        lock = threading.Lock()
        release = threading.Event()

        def work():
            nonlocal entered, peak
            with lock:
                entered += 1
                peak = max(peak, entered)
            release.wait(1.0)
            with lock:
                entered -= 1

        threads = [
            threading.Thread(target=lambda: gate.interactive_call(work), name=f"glyph-row_{i}")
            for i in range(3)
        ]
        for thread in threads:
            thread.start()
        deadline = time.time() + 1.0
        while time.time() < deadline:
            with lock:
                if peak >= 3:
                    break
            time.sleep(0.01)
        release.set()
        for thread in threads:
            thread.join(1.0)

        self.assertEqual(peak, 3)


if __name__ == "__main__":
    unittest.main()
