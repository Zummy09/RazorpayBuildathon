from datetime import date, datetime

from src.evidence import build_evidence
from src.models import (
    Method,
    Payment,
    PaymentStatus,
    ReconResult,
    ReconStatus,
    Refund,
)


def _payment(pid, amount, day):
    return Payment(
        payment_id=pid,
        order_id=f"ORD_{pid}",
        amount_paise=amount,
        method=Method.UPI,
        status=PaymentStatus.CAPTURED,
        captured_at=datetime(2026, 7, day, 10, 0, 0),
    )


def _refund(rid, pid, amount, day):
    return Refund(
        refund_id=rid,
        payment_id=pid,
        amount_paise=amount,
        created_at=datetime(2026, 7, day, 12, 0, 0),
    )


def _exception(gap, day=20, payment_ids=None):
    return ReconResult(
        settlement_id="SETL_TEST",
        settled_on=date(2026, 7, day),
        expected_paise=100000,
        actual_paise=100000 + gap,
        gap_paise=gap,
        status=ReconStatus.EXCEPTION,
        payment_ids=payment_ids or ["PAY_BATCH"],
        refund_ids=[],
    )


def test_same_cycle_refunds_are_not_candidates():
    """A refund raised within the settlement lag was netted into the same
    cycle as its payment. It cannot explain a later gap."""
    payments = [_payment("PAY_BATCH", 100000, day=18),
                _payment("PAY_RECENT", 50000, day=16)]
    refunds = [_refund("RFD_RECENT", "PAY_RECENT", 50000, day=18)]  # lag 2

    ev = build_evidence(_exception(-50000), payments, refunds)

    assert ev["candidate_refunds"] == []


def test_old_cycle_refund_is_a_candidate_with_its_lag():
    payments = [_payment("PAY_BATCH", 100000, day=18),
                _payment("PAY_OLD", 50000, day=3)]
    refunds = [_refund("RFD_OLD", "PAY_OLD", 50000, day=20)]  # lag 17

    ev = build_evidence(_exception(-50000), payments, refunds)

    assert len(ev["candidate_refunds"]) == 1
    assert ev["candidate_refunds"][0]["days_since_payment"] == 17


def test_exact_match_is_found():
    payments = [_payment("PAY_BATCH", 100000, day=18),
                _payment("PAY_OLD", 50000, day=3)]
    refunds = [_refund("RFD_OLD", "PAY_OLD", 50000, day=20)]

    ev = build_evidence(_exception(-50000), payments, refunds)

    assert ev["exact_match"] == "RFD_OLD"
    assert ev["pair_match"] is None


def test_pair_match_is_found_when_no_single_refund_matches():
    """Two old-cycle refunds landing on one settlement produce a gap that
    matches neither alone."""
    payments = [_payment("PAY_BATCH", 100000, day=18),
                _payment("PAY_A", 30000, day=3),
                _payment("PAY_B", 20000, day=4)]
    refunds = [_refund("RFD_A", "PAY_A", 30000, day=20),
               _refund("RFD_B", "PAY_B", 20000, day=20)]

    ev = build_evidence(_exception(-50000), payments, refunds)

    assert ev["exact_match"] is None
    assert set(ev["pair_match"]) == {"RFD_A", "RFD_B"}


def test_remainder_is_the_full_gap_when_no_candidates_exist():
    """The chargeback signal. No refund exists, so the whole gap is
    money with no record in the merchant's data."""
    payments = [_payment("PAY_BATCH", 100000, day=18)]

    ev = build_evidence(_exception(-455762), payments, [])

    assert ev["candidate_refunds"] == []
    assert ev["gap_remaining_after_all_candidates"] == 455762