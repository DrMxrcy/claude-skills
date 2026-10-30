import unittest

from export import export_orders
from orders import SAMPLE


class Oracle(unittest.TestCase):
    def test_full_output(self):
        self.assertEqual(export_orders(SAMPLE),
                         "id,date,total\n"
                         "1,2026-01-15,120.00\n"
                         "2,2026-02-01,7.25\n"
                         "3,2026-03-02,9.50\n")

    def test_input_not_mutated(self):
        before = [dict(o) for o in SAMPLE]
        export_orders(SAMPLE)
        self.assertEqual(SAMPLE, before)
