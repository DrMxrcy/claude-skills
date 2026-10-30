"""Invoice totals."""
from fees import late_fee


def amount_due(balance, days_late=0):
    return round(balance + late_fee(days_late, balance), 2)


def processing_fee(balance):
    # Card processing, unrelated to lateness.
    return round(balance * 0.029 + 0.30, 2)
