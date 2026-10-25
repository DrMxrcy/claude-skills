"""Late fees for overdue invoices."""

GRACE_DAYS = 3
DAILY_RATE = 0.001  # 0.1% of the balance per day past grace


def late_fee(days_late, balance):
    """Fee owed on an invoice paid `days_late` days after its due date."""
    billable = max(0, days_late - GRACE_DAYS)
    return round(balance * DAILY_RATE * billable, 2)
