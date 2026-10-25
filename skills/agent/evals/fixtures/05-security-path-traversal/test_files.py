import os
import tempfile
import unittest

from files import read_upload


class FilesTest(unittest.TestCase):
    def test_reads_nested_upload(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "a"))
            with open(os.path.join(root, "a", "x.txt"), "wb") as f:
                f.write(b"hi")
            self.assertEqual(read_upload(root, "a/x.txt"), b"hi")


if __name__ == "__main__":
    unittest.main()
