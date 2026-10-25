import os
import unittest

import cli
import config


class ConfigTest(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("APP_TIMEOUT", None)

    def test_default(self):
        self.assertEqual(config.get("timeout"), 30)

    def test_cli_override(self):
        self.assertEqual(cli.main(["x", "--timeout", "7"])["timeout"], 7)


if __name__ == "__main__":
    unittest.main()
