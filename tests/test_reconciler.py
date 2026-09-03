from datetime import datetime

import pytest

from src.models import Method, Payment, PaymentStatus, Refund, ReconStatus, Settlement
from src.reconciler import reconcile_all


def _payment(pid, amount, day, status=PaymentStatus.CAPTURED):
    return Payment(
        payment_id=pid,
        order_id=f"ORD_{pid}",
        amount_paise=amount,
        method=Method.UPI,          # zero fee keeps the arithmetic clean
        status=status,
        captured_at=datetime(2026, 7, day, 10, 0, 0),
    )


def _settlement(sid, amount, day):
    return Settlement(
        settlement_id=sid,
        utr=f"UTR{sid}",
        net_amount_paise=amount,
        settled_at=datetime(2026, 7, day, 11, 0, 0),
    )


def test_settlement_matches_payments_from_two_days_earlier():
    """T+2. A settlement pays for the batch captured two days before,
    not the same day."""
    payments = [_payment("PAY_1", 100000, day=10)]
    settlements = [_settlement("SETL_1", 100000, day=12)]

    result = reconcile_all(payments, [], settlements)[0]

    assert result.status == ReconStatus.MATCHED
    assert result.payment_ids == ["PAY_1"]


def test_failed_payments_are_excluded_from_the_batch():
    """F-01. A failed payment never reaches the bank, so it must not
    appear in the rebuilt settlement."""
    payments = [
        _payment("PAY_1", 100000, day=10),
        _payment("PAY_2", 500000, day=10, status=PaymentStatus.FAILED),
    ]
    settlements = [_settlement("SETL_1", 100000, day=12)]

    result = reconcile_all(payments, [], settlements)[0]

    assert result.status == ReconStatus.MATCHED
    assert "PAY_2" not in result.payment_ids


def test_refund_is_subtracted_when_its_payment_is_in_the_batch():
    payments = [_payment("PAY_1", 100000, day=10)]
    refunds = [
        Refund(
            refund_id="RFD_1",
            payment_id="PAY_1",
            amount_paise=30000,
            created_at=datetime(2026, 7, 12, 12, 0, 0),
        )
    ]
    settlements = [_settlement("SETL_1", 70000, day=12)]

    result = reconcile_all(payments, refunds, settlements)[0]

    assert result.status == ReconStatus.MATCHED
    assert result.refund_ids == ["RFD_1"]


def test_old_cycle_refund_is_not_subtracted_and_leaves_a_gap():
    """F-03. The reconciler sees this refund but cannot prove it belongs
    to this settlement, so it refuses to count it. The unexplained
    remainder is the exception the classifier has to explain."""
    payments = [
        _payment("PAY_OLD", 200000, day=3),    # settled on the 5th
        _payment("PAY_NEW", 100000, day=10),   # this batch
    ]
    refunds = [
        Refund(
            refund_id="RFD_OLD",
            payment_id="PAY_OLD",
            amount_paise=200000,
            created_at=datetime(2026, 7, 12, 12, 0, 0),
        )
    ]
    # bank deducted the old refund; the reconciler cannot account for it
    settlements = [_settlement("SETL_1", 100000 - 200000, day=12)]

    result = reconcile_all(payments, refunds, settlements)[0]

    assert result.status == ReconStatus.EXCEPTION
    assert result.gap_paise == -200000
    assert result.refund_ids == []          # seen, but not counted