import unittest

from swedish_wordlist_tools.artifact_paths import SAOL14_GAMEWORDS
from swedish_wordlist_tools.build_game_wordlist_pipeline import DEFAULT_OUTPUT as PIPELINE_OUTPUT
from swedish_wordlist_tools.game_wordlist import DEFAULT_OUTPUT as GAME_WORDLIST_OUTPUT


class GamewordsArtifactPathTests(unittest.TestCase):
    def test_all_gameword_exports_use_the_canonical_path(self):
        self.assertEqual(SAOL14_GAMEWORDS, GAME_WORDLIST_OUTPUT)
        self.assertEqual(SAOL14_GAMEWORDS, PIPELINE_OUTPUT)
        self.assertEqual("data/processed/saol14-gamewords.txt", SAOL14_GAMEWORDS.as_posix())


if __name__ == "__main__":
    unittest.main()
