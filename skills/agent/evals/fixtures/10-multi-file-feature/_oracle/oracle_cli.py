import contextlib
import io
import json
import unittest

import cli


def run(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = cli.main(argv)
    return code, buf.getvalue()


class Oracle(unittest.TestCase):
    def test_json_sorted_by_id(self):
        code, out = run(["list", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), [
            {"id": 1, "title": "buy milk", "done": True},
            {"id": 2, "title": "write tests", "done": False},
        ])

    def test_text_unchanged(self):
        self.assertEqual(run(["list"]), (0, "[ ] 2 write tests\n[x] 1 buy milk\n"))
