import os
import tempfile
import unittest
from pathlib import Path

from keren.env import load_env


class LoadEnv(unittest.TestCase):
    def test_loads_without_overriding(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / ".env"
            f.write_text("# c\nKEREN_T1=abc\nKEREN_T2='q'\nKEREN_T3=fromfile\n")
            os.environ["KEREN_T3"] = "real"
            try:
                self.assertTrue(load_env(f))
                self.assertEqual((os.environ["KEREN_T1"], os.environ["KEREN_T2"], os.environ["KEREN_T3"]),
                                 ("abc", "q", "real"))
            finally:
                for k in ("KEREN_T1", "KEREN_T2", "KEREN_T3"):
                    os.environ.pop(k, None)

    def test_missing_file(self):
        self.assertFalse(load_env(Path("/nonexistent/.env")))


if __name__ == "__main__":
    unittest.main()
