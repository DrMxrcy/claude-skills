import unittest

from temps import c_to_f, f_to_c


class TempsTest(unittest.TestCase):
    def test_c_to_f(self):
        self.assertEqual(c_to_f(100), 212.0)
        self.assertEqual(c_to_f(-40), -40.0)

    def test_f_to_c(self):
        self.assertEqual(f_to_c(212), 100.0)
        self.assertEqual(f_to_c(-40), -40.0)
        self.assertEqual(f_to_c(0), -17.8)

    def test_round_trip(self):
        for c in (-40, 0, 37, 100):
            self.assertEqual(f_to_c(c_to_f(c)), c)


if __name__ == "__main__":
    unittest.main()
