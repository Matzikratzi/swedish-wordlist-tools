import threading
import time
import unittest

from swedish_wordlist_tools.ocr_review_five_rows_glyphs_fast_html import SynchronizedStateCache


class FastFiveRowGlyphReviewTests(unittest.TestCase):
    def test_concurrent_requests_compute_row_once(self):
        calls = []

        def loader(position):
            calls.append(position)
            time.sleep(0.03)
            return {"position": position}

        cache = SynchronizedStateCache(loader)
        results = []
        threads = [threading.Thread(target=lambda: results.append(cache.get((0, 10)))) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(calls, [(0, 10)])
        self.assertEqual(len(results), 8)
        self.assertTrue(all(result == {"position": (0, 10)} for result in results))

    def test_clear_forces_one_new_calculation(self):
        calls = []

        def loader(position):
            calls.append(position)
            return {"position": position, "generation": len(calls)}

        cache = SynchronizedStateCache(loader)
        first = cache.get((0, 3))
        again = cache.get((0, 3))
        cache.clear("test")
        after = cache.get((0, 3))

        self.assertIs(first, again)
        self.assertEqual(len(calls), 2)
        self.assertNotEqual(first["generation"], after["generation"])


if __name__ == "__main__":
    unittest.main()
