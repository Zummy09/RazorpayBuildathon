"""Assembles the evidence package for one unexplained settlement gap.

Everything here is deterministic. The classifier receives facts, never
raw data to compute over -- amount matching is done in Python so the
model only has to judge which explanation fits.
"""

from datetime import timedelta
from itertools import combinations

from src.models import Payment, ReconResult, Refund

LOOKBACK_DAYS = 30
SETTLEMENT_LAG_DAYS = 2


def build_evidence(
    result: ReconResult,
    payments: list[Payment],
    refunds: list[Refund],
) -> dict:
    """Gather plausible causes for one settlement gap."""
    gap = abs(result.gap_paise)
    settled_on = result.settled_on
    batch_capture_date = settled_on - timedelta(days=SETTLEMENT_LAG_DAYS)

    payments_by_id = {p.payment_id: p for p in payments}
    batch_ids = set(result.payment_ids)
    already_explained = set(result.refund_ids)

    window_start = settled_on - timedelta(days=LOOKBACK_DAYS)

    candidates = []
    for r in refunds:
        if r.refund_id in already_explained:
            continue
        if not (window_start <= r.created_at.date() <= settled_on):
            continue
        if r.payment_id in batch_ids:
            continue

        original = payments_by_id.get(r.payment_id)
        if original is None:
            continue

        captured_on = original.captured_at.date()

        # a refund raised within the settlement lag was netted into the
        # same cycle as its payment -- it cannot be an old-cycle deduction
        if (r.created_at.date() - captured_on).days <= SETTLEMENT_LAG_DAYS:
            continue

        candidates.append(
            {
                "refund_id": r.refund_id,
                "amount_paise": r.amount_paise,
                "created_on": r.created_at.date().isoformat(),
                "original_payment": r.payment_id,
                "original_captured_on": captured_on.isoformat(),
                "days_since_payment": (r.created_at.date() - captured_on).days,
            }
        )

    exact_match = next(
        (c["refund_id"] for c in candidates if c["amount_paise"] == gap), None
    )

    pair_match = None
    if exact_match is None:
        for a, b in combinations(candidates, 2):
            if a["amount_paise"] + b["amount_paise"] == gap:
                pair_match = [a["refund_id"], b["refund_id"]]
                break

    # how much of the gap survives the best single candidate. a large
    # remainder means part of the gap has no record in the merchant's data.
    largest_candidate = max(
        (c["amount_paise"] for c in candidates), default=0
    )
    remainder = gap - largest_candidate

    total_candidates = sum(c["amount_paise"] for c in candidates)

    return {
        "settlement_id": result.settlement_id,
        "settled_on": settled_on.isoformat(),
        "expected_paise": result.expected_paise,
        "actual_paise": result.actual_paise,
        "gap_paise": result.gap_paise,
        "gap_direction": "short" if result.gap_paise < 0 else "over",
        "batch_capture_date": batch_capture_date.isoformat(),
        "batch_size": len(batch_ids),
        "refunds_already_explained": len(already_explained),
        "candidate_refunds": candidates,
        "exact_match": exact_match,
        "pair_match": pair_match,
        "largest_candidate_paise": largest_candidate,
        "gap_remaining_after_largest_candidate": remainder,
        "all_candidates_total_paise": total_candidates,
        "gap_remaining_after_all_candidates": gap - total_candidates,
    }