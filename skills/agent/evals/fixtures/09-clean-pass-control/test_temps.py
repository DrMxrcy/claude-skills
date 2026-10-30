import unittest

from temps import c_to_f


class TempsTest(unittest.TestCase):
    def test_c_to_f(self):
        self.assertEqual(c_to_f(100), 212.0)
        self.assertEqual(c_to_f(-40), -40.0)


if __name__ == "__main__":
    unittest.main()
