import threading
import time
import unittest

from swedish_wordlist_tools.ocr_review_five_rows_glyphs_fast_html import SynchronizedStateCache


class FastFiveRowGlyphReviewTests(unittest.TestCase):
    def test_concurrent_requests_compute_same_row_once(self):
        calls = []

        def loader(position):
            calls.append(position)
            time.sleep(0.03)
            return {"position": position, "covered_pixels": 9, "source_pixels": 10}

        cache = SynchronizedStateCache(loader)
        results = []
        threads = [threading.Thread(target=lambda: results.append(cache.get((0, 10)))) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(calls, [(0, 10)])
        self.assertEqual(len(results), 8)

    def test_different_rows_are_not_serialised_by_global_lock(self):
        entered = []
        both_entered = threading.Event()
        release = threading.Event()
        guard = threading.Lock()

        def loader(position):
            with guard:
                entered.append(position)
                if len(entered) == 2:
                    both_entered.set()
            release.wait(1.0)
            return {"position": position, "covered_pixels": 9, "source_pixels": 10}

        cache = SynchronizedStateCache(loader)
        threads = [threading.Thread(target=lambda p=p: cache.get(p)) for p in [(0, 1), (0, 2)]]
        for thread in threads:
            thread.start()
        self.assertTrue(both_entered.wait(0.5), "different rows should be allowed to analyse concurrently")
        release.set()
        for thread in threads:
            thread.join()
        self.assertCountEqual(entered, [(0, 1), (0, 2)])

    def test_facit_change_keeps_old_exact_row_for_defect_scan(self):
        calls = []

        def loader(position):
            calls.append(position)
            return {"position": position, "covered_pixels": 10, "source_pixels": 10, "generation": len(calls)}

        cache = SynchronizedStateCache(loader)
        first = cache.get((0, 3))
        cache.facit_changed("test")
        scan = cache.get_for_defect_scan((0, 3))

        self.assertIs(first, scan)
        self.assertEqual(len(calls), 1)

    def test_facit_change_recomputes_old_defective_row_for_defect_scan(self):
        calls = []

        def loader(position):
            calls.append(position)
            return {"position": position, "covered_pixels": 9, "source_pixels": 10, "generation": len(calls)}

        cache = SynchronizedStateCache(loader)
        first = cache.get((0, 3))
        cache.facit_changed("test")
        after = cache.get_for_defect_scan((0, 3))

        self.assertEqual(len(calls), 2)
        self.assertNotEqual(first["generation"], after["generation"])

    def test_normal_get_refreshes_even_old_exact_row(self):
        calls = []

        def loader(position):
            calls.append(position)
            return {"position": position, "covered_pixels": 10, "source_pixels": 10, "generation": len(calls)}

        cache = SynchronizedStateCache(loader)
        first = cache.get((0, 3))
        cache.facit_changed("test")
        after = cache.get((0, 3))

        self.assertEqual(len(calls), 2)
        self.assertNotEqual(first["generation"], after["generation"])

    def test_hard_clear_forces_new_calculation(self):
        calls = []

        def loader(position):
            calls.append(position)
            return {"position": position, "covered_pixels": 10, "source_pixels": 10, "generation": len(calls)}

        cache = SynchronizedStateCache(loader)
        first = cache.get((0, 3))
        cache.clear("test")
        after = cache.get((0, 3))

        self.assertEqual(len(calls), 2)
        self.assertNotEqual(first["generation"], after["generation"])


if __name__ == "__main__":
    unittest.main()
