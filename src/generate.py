import csv
import random
from datetime import date, datetime, timedelta

from src.models import Method, PaymentStatus, Payment

SEED = 42
START_DATE = date(2026, 7, 1)
DAYS = 30

WEEKDAY_TXN_RANGE = (40, 60)
WEEKEND_FACTOR = 0.6

METHODS = [Method.UPI, Method.CARD, Method.NETBANKING]
METHOD_WEIGHTS = [70, 20, 10]

FAILURE_RATE = 0.08
AMOUNT_RANGE_PAISE = (20_000, 1_500_000)


def _txn_count_for(day: date) -> int:
    """How many transactions happen on this day. Weekends are quieter."""
    base = random.randint(*WEEKDAY_TXN_RANGE)
    if day.weekday() >= 5:
        return int(base * WEEKEND_FACTOR)
    return base


def _random_time_on(day: date) -> datetime:
    """A random moment during business hours on the given day."""
    hour = random.randint(8, 21)
    minute = random.randint(0, 59)
    second = random.randint(0, 59)
    return datetime(day.year, day.month, day.day, hour, minute, second)


def generate_payments() -> list[Payment]:
    random.seed(SEED)
    payments = []
    counter = 1

    for offset in range(DAYS):
        day = START_DATE + timedelta(days=offset)

        for _ in range(_txn_count_for(day)):
            amount = random.randint(*AMOUNT_RANGE_PAISE)
            method = random.choices(METHODS, weights=METHOD_WEIGHTS)[0]

            if random.random() < FAILURE_RATE:
                status = PaymentStatus.FAILED
            else:
                status = PaymentStatus.CAPTURED

            payments.append(
                Payment(
                    payment_id=f"PAY_{counter:05d}",
                    order_id=f"ORD_{counter:05d}",
                    amount_paise=amount,
                    method=method,
                    status=status,
                    captured_at=_random_time_on(day),
                )
            )
            counter += 1

    return payments


def write_payments_csv(payments: list[Payment], path: str) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["payment_id", "order_id", "amount_paise", "method", "status", "captured_at"]
        )
        for p in payments:
            writer.writerow(
                [
                    p.payment_id,
                    p.order_id,
                    p.amount_paise,
                    p.method.value,
                    p.status.value,
                    p.captured_at.isoformat(),
                ]
            )


if __name__ == "__main__":
    payments = generate_payments()
    write_payments_csv(payments, "data/payments.csv")
    print(f"wrote {len(payments)} payments")