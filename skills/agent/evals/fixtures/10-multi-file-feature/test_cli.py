import contextlib
import io
import unittest

import cli


class CliTest(unittest.TestCase):
    def test_list_text(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(cli.main(["list"]), 0)
        self.assertEqual(buf.getvalue(), "[ ] 2 write tests\n[x] 1 buy milk\n")


if __name__ == "__main__":
    unittest.main()
