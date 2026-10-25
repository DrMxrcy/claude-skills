import unittest

from temps import c_to_f, f_to_c


class Oracle(unittest.TestCase):
    def test_values(self):
        self.assertEqual(f_to_c(212), 100.0)
        self.assertEqual(f_to_c(98.6), 37.0)
        self.assertEqual(f_to_c(0), -17.8)
        self.assertEqual(c_to_f(37), 98.6)
