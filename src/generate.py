import csv
import random
from datetime import date, datetime, timedelta

from src.models import Method, PaymentStatus, Payment, Refund, Settlement

from collections import defaultdict

from src.fees import total_deduction_paise



SEED = 42
START_DATE = date(2026, 7, 1)
DAYS = 30

WEEKDAY_TXN_RANGE = (40, 60)
WEEKEND_FACTOR = 0.6

METHODS = [Method.UPI, Method.CARD, Method.NETBANKING]
METHOD_WEIGHTS = [70, 20, 10]

FAILURE_RATE = 0.08
AMOUNT_RANGE_PAISE = (20_000, 1_500_000)

SETTLEMENT_LAG_DAYS = 2

NORMAL_REFUND_COUNT = 60
OLD_CYCLE_REFUND_COUNT = 10
OLD_CYCLE_LAG_RANGE = (15, 25)
NORMAL_REFUND_LAG_RANGE = (1, 2)
PARTIAL_REFUND_MIN_FRACTION = 0.3


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

def build_settlements(
    payments: list[Payment], refunds: list[Refund]
) -> list[Settlement]:
    by_date = defaultdict(list)
    for p in payments:
        if p.status == PaymentStatus.CAPTURED:
            by_date[p.captured_at.date()].append(p)

    refunds_by_date = defaultdict(int)
    for r in refunds:
        refunds_by_date[r.created_at.date()] += r.amount_paise

    settlements = []
    counter = 1

    for capture_date in sorted(by_date):
        batch = by_date[capture_date]

        gross = sum(p.amount_paise for p in batch)
        deductions = sum(
            total_deduction_paise(p.amount_paise, p.method) for p in batch
        )

        settled_on = capture_date + timedelta(days=SETTLEMENT_LAG_DAYS)
        refunded = refunds_by_date.get(settled_on, 0)

        net = gross - deductions - refunded

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


#Refunds

def generate_refunds(payments: list[Payment]) -> tuple[list[Refund], list[dict]]:
    """Create refunds. Old-cycle ones are planted deliberately and recorded
    in ground truth, because they are the exceptions the system must explain."""
    captured = [p for p in payments if p.status == PaymentStatus.CAPTURED]
    last_day = START_DATE + timedelta(days=DAYS - 1)

    refunds = []
    ground_truth = []
    counter = 1

    # payments early enough to allow a long lag and still land in the window
    early = [
        p for p in captured
        if p.captured_at.date() < START_DATE + timedelta(days=10)
    ]

    old_cycle_targets = random.sample(early, OLD_CYCLE_REFUND_COUNT)

    for p in old_cycle_targets:
        lag = random.randint(*OLD_CYCLE_LAG_RANGE)
        refund_date = p.captured_at.date() + timedelta(days=lag)
        if refund_date > last_day:
            refund_date = last_day

        refunds.append(
            Refund(
                refund_id=f"RFD_{counter:04d}",
                payment_id=p.payment_id,
                amount_paise=p.amount_paise,
                created_at=datetime(
                    refund_date.year, refund_date.month, refund_date.day, 12, 0, 0
                ),
            )
        )
        ground_truth.append(
            {
                "settled_on": refund_date.isoformat(),
                "cause": "old_cycle_refund",
                "gap_paise": p.amount_paise,
                "caused_by": f"RFD_{counter:04d}",
                "original_payment": p.payment_id,
            }
        )
        counter += 1

    # normal refunds, settled close to the original payment
    old_cycle_ids = {p.payment_id for p in old_cycle_targets}
    remaining = [p for p in captured if p.payment_id not in old_cycle_ids]
    
    for p in random.sample(remaining, NORMAL_REFUND_COUNT):
        lag = random.randint(*NORMAL_REFUND_LAG_RANGE)
        refund_date = p.captured_at.date() + timedelta(days=lag)
        if refund_date > last_day:
            continue

        fraction = random.uniform(PARTIAL_REFUND_MIN_FRACTION, 1.0)
        amount = int(p.amount_paise * fraction)

        refunds.append(
            Refund(
                refund_id=f"RFD_{counter:04d}",
                payment_id=p.payment_id,
                amount_paise=amount,
                created_at=datetime(
                    refund_date.year, refund_date.month, refund_date.day, 12, 0, 0
                ),
            )
        )
        counter += 1

    return refunds, ground_truth


def write_refunds_csv(refunds: list[Refund], path: str) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["refund_id", "payment_id", "amount_paise", "created_at"])
        for r in refunds:
            writer.writerow(
                [r.refund_id, r.payment_id, r.amount_paise, r.created_at.isoformat()]
            )


def write_ground_truth_csv(rows: list[dict], path: str) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "settled_on",
                "cause",
                "gap_paise",
                "caused_by",
                "original_payment",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

if __name__ == "__main__":
    payments = generate_payments()
    refunds, truth = generate_refunds(payments)
    settlements = build_settlements(payments, refunds)

    write_payments_csv(payments, "data/payments.csv")
    write_refunds_csv(refunds, "data/refunds.csv")
    write_settlements_csv(settlements, "data/settlements.csv")
    write_ground_truth_csv(truth, "data/ground_truth.csv")

    print(f"payments     {len(payments)}")
    print(f"refunds      {len(refunds)}")
    print(f"settlements  {len(settlements)}")
    print(f"ground truth {len(truth)}")