"""Rebuilds each settlement from the merchant's own records and compares
it to what the bank actually credited.

This module must never read data/ground_truth.csv. Ground truth is for
evaluation only.

The reconciler is deliberately limited to what a real merchant knows:
their own payments, their own refunds, and the net bank credit. It is
NOT told which refunds the gateway netted against which settlement --
working that out is the problem being solved.
"""

from collections import defaultdict
from datetime import timedelta

from src.models import (
    Payment,
    PaymentStatus,
    ReconResult,
    ReconStatus,
    Refund,
    Settlement,
)
from src.fees import total_deduction_paise

SETTLEMENT_LAG_DAYS = 2
TOLERANCE_PAISE = 0


def _index_payments(payments: list[Payment]) -> dict:
    """Captured payments grouped by the date they were captured."""
    by_date = defaultdict(list)
    for p in payments:
        if p.status == PaymentStatus.CAPTURED:
            by_date[p.captured_at.date()].append(p)
    return by_date


def _index_refunds(refunds: list[Refund]) -> dict:
    """Refunds grouped by the date they were created."""
    by_date = defaultdict(list)
    for r in refunds:
        by_date[r.created_at.date()].append(r)
    return by_date


def reconcile_one(
    settlement: Settlement,
    payments_by_date: dict,
    refunds_by_date: dict,
) -> ReconResult:
    """Rebuild one settlement and compare it to the bank credit."""
    settled_on = settlement.settled_at.date()
    capture_date = settled_on - timedelta(days=SETTLEMENT_LAG_DAYS)

    batch = payments_by_date.get(capture_date, [])
    batch_payment_ids = {p.payment_id for p in batch}

    # only refunds whose original payment is in this batch can be
    # accounted for. anything else is money the merchant cannot explain.
    explained_refunds = [
        r
        for r in refunds_by_date.get(settled_on, [])
        if r.payment_id in batch_payment_ids
    ]

    gross = sum(p.amount_paise for p in batch)
    deductions = sum(
        total_deduction_paise(p.amount_paise, p.method) for p in batch
    )
    refunded = sum(r.amount_paise for r in explained_refunds)

    expected = gross - deductions - refunded
    gap = settlement.net_amount_paise - expected

    if abs(gap) <= TOLERANCE_PAISE:
        status = ReconStatus.MATCHED
    else:
        status = ReconStatus.EXCEPTION

    return ReconResult(
        settlement_id=settlement.settlement_id,
        settled_on=settled_on,
        expected_paise=expected,
        actual_paise=settlement.net_amount_paise,
        gap_paise=gap,
        status=status,
        payment_ids=[p.payment_id for p in batch],
        refund_ids=[r.refund_id for r in explained_refunds],
    )


def reconcile_all(
    payments: list[Payment],
    refunds: list[Refund],
    settlements: list[Settlement],
) -> list[ReconResult]:
    """Reconcile every settlement. Indexes are built once, not per call."""
    payments_by_date = _index_payments(payments)
    refunds_by_date = _index_refunds(refunds)

    return [
        reconcile_one(s, payments_by_date, refunds_by_date)
        for s in settlements
    ]