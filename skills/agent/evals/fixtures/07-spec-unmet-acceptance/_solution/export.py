"""CSV export of orders."""
import csv
import io


def export_orders(orders):
    """Return orders as CSV text with a header row."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["id", "date", "total"])
    for order in sorted(orders, key=lambda o: o["date"]):
        writer.writerow([order["id"], order["date"], f"{order['total']:.2f}"])
    return out.getvalue()
