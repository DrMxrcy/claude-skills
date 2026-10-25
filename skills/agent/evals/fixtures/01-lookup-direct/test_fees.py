import unittest

from fees import late_fee
from invoice import amount_due


class FeesTest(unittest.TestCase):
    def test_no_fee_inside_grace(self):
        self.assertEqual(late_fee(3, 1000), 0)

    def test_fee_after_grace(self):
        self.assertEqual(late_fee(5, 1000), 2.0)

    def test_amount_due(self):
        self.assertEqual(amount_due(1000, 5), 1002.0)


if __name__ == "__main__":
    unittest.main()
