import unittest

from export import export_orders
from orders import SAMPLE


class ExportTest(unittest.TestCase):
    def test_header_row(self):
        self.assertEqual(export_orders(SAMPLE).splitlines()[0], "id,date,total")

    def test_totals_two_decimals(self):
        lines = export_orders([{"id": 1, "date": "2026-01-15", "total": 7.5}]).splitlines()
        self.assertEqual(lines[1], "1,2026-01-15,7.50")


if __name__ == "__main__":
    unittest.main()
