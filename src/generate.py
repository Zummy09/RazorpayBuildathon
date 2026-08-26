import csv
import random
from datetime import date, datetime, timedelta

from src.models import Method, PaymentStatus, Payment

from collections import defaultdict

from src.models import Settlement
from src.fees import total_deduction_paise

SETTLEMENT_LAG_DAYS = 2


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


#Settlement

def build_settlements(payments: list[Payment]) -> list[Settlement]:
    """Group payments by capture date and settle each batch T+2."""
    by_date = defaultdict(list)
    for p in payments:
        by_date[p.captured_at.date()].append(p)

    settlements = []
    counter = 1

    for capture_date in sorted(by_date):
        batch = [p for p in by_date[capture_date] if p.status == PaymentStatus.CAPTURED]

        gross = sum(p.amount_paise for p in batch)
        deductions = sum(
            total_deduction_paise(p.amount_paise, p.method) for p in batch
        )
        net = gross - deductions

        settled_on = capture_date + timedelta(days=SETTLEMENT_LAG_DAYS)
        settled_at = datetime(
            settled_on.year, settled_on.month, settled_on.day, 11, 0, 0
        )

        settlements.append(
            Settlement(
                settlement_id=f"SETL_{counter:03d}",
                utr=f"HDFC{settled_on.strftime('%Y%m%d')}01",
                net_amount_paise=net,
                settled_at=settled_at,
            )
        )
        counter += 1

    return settlements

def write_settlements_csv(settlements: list[Settlement], path: str) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["settlement_id", "utr", "net_amount_paise", "settled_at"])
        for s in settlements:
            writer.writerow(
                [
                    s.settlement_id,
                    s.utr,
                    s.net_amount_paise,
                    s.settled_at.isoformat(),
                ]
            )


if __name__ == "__main__":
    payments = generate_payments()
    write_payments_csv(payments, "data/payments.csv")
    print(f"wrote {len(payments)} payments")

    settlements = build_settlements(payments)
    write_settlements_csv(settlements, "data/settlements.csv")
    print(f"wrote {len(settlements)} settlements")