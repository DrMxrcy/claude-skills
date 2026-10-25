import os
import tempfile
import unittest

from files import read_upload


class Oracle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = self.tmp.name
        self.root = os.path.join(base, "uploads")
        os.makedirs(os.path.join(self.root, "a"))
        with open(os.path.join(self.root, "a", "x.txt"), "wb") as f:
            f.write(b"ok")
        self.secret = os.path.join(base, "secret.txt")
        with open(self.secret, "wb") as f:
            f.write(b"secret")
        os.symlink(self.secret, os.path.join(self.root, "link.txt"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_nested_file_still_served(self):
        self.assertEqual(read_upload(self.root, "a/x.txt"), b"ok")

    def test_dotdot_rejected(self):
        with self.assertRaises(PermissionError):
            read_upload(self.root, "../secret.txt")
        with self.assertRaises(PermissionError):
            read_upload(self.root, "a/../../secret.txt")

    def test_absolute_rejected(self):
        with self.assertRaises(PermissionError):
            read_upload(self.root, self.secret)

    def test_symlink_escape_rejected(self):
        with self.assertRaises(PermissionError):
            read_upload(self.root, "link.txt")

    def test_sibling_prefix_rejected(self):
        sibling = self.root + "-evil"
        os.makedirs(sibling)
        with open(os.path.join(sibling, "y.txt"), "wb") as f:
            f.write(b"evil")
        with self.assertRaises(PermissionError):
            read_upload(self.root, "../uploads-evil/y.txt")
