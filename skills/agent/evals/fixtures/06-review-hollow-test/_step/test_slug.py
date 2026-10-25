import unittest

from slug import slugify, unique_slug


class SlugTest(unittest.TestCase):
    def test_slugify(self):
        self.assertEqual(slugify("Hello, World!"), "hello-world")

    def test_unique_slug_unused(self):
        self.assertEqual(unique_slug("Hello", set()), "hello")

    def test_unique_slug_suffixes(self):
        existing = {"hello", "hello-2"}
        result = unique_slug("Hello", existing)
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
