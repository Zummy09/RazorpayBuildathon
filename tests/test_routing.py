from src.models import Cause, CauseAttribution, ExceptionVerdict, Route
from src.pipeline import resolve_deterministically, route_verdict


def _verdict(causes, confidence):
    """causes is a list of (Cause, amount_paise) tuples."""
    return ExceptionVerdict(
        causes=[
            CauseAttribution(cause=c, amount_paise=amt, evidence_refund_ids=[])
            for c, amt in causes
        ],
        confidence=confidence,
        reasoning="test",
        suggested_action="test",
    )


def test_fully_covered_high_confidence_auto_resolves():
    v = _verdict([(Cause.OLD_CYCLE_REFUND, 50000)], 0.95)
    assert route_verdict(v, -50000) == Route.AUTO_RESOLVED


def test_low_confidence_escalates_even_when_fully_covered():
    v = _verdict([(Cause.OLD_CYCLE_REFUND, 50000)], 0.40)
    assert route_verdict(v, -50000) == Route.ESCALATED


def test_partial_coverage_escalates_despite_high_confidence():
    """F-12. A gap 58% explained escalates however certain the model is.
    Coverage is arithmetic on the returned amounts, not a model opinion."""
    v = _verdict([(Cause.CHARGEBACK, 29000)], 0.99)
    assert route_verdict(v, -50000) == Route.ESCALATED


def test_multi_cause_verdict_sums_to_full_coverage():
    """A gap that is part refund and part chargeback is representable."""
    v = _verdict(
        [(Cause.OLD_CYCLE_REFUND, 30000), (Cause.CHARGEBACK, 20000)], 0.90
    )
    assert v.attributed_paise == 50000
    assert route_verdict(v, -50000) == Route.AUTO_RESOLVED


def test_unknown_remainder_drags_coverage_down():
    """The model explains 60% and marks the rest unknown. The primary
    cause is still the refund, but the verdict escalates."""
    v = _verdict(
        [(Cause.OLD_CYCLE_REFUND, 30000), (Cause.UNKNOWN, 20000)], 0.95
    )
    assert v.primary_cause == Cause.OLD_CYCLE_REFUND
    assert route_verdict(v, -50000) == Route.ESCALATED


def test_empty_causes_is_unresolvable():
    v = _verdict([], 0.0)
    assert route_verdict(v, -50000) == Route.UNRESOLVABLE


def test_unknown_primary_is_unresolvable():
    v = _verdict([(Cause.UNKNOWN, 50000)], 0.95)
    assert route_verdict(v, -50000) == Route.UNRESOLVABLE


def test_single_exact_match_resolves_without_the_model():
    evidence = {
        "gap_paise": -50000,
        "exact_match": "RFD_0001",
        "pair_match": None,
        "candidate_refunds": [{"refund_id": "RFD_0001", "amount_paise": 50000}],
        "gap_remaining_after_all_candidates": 0,
    }
    verdict = resolve_deterministically(evidence)

    assert verdict is not None
    assert verdict.primary_cause == Cause.OLD_CYCLE_REFUND
    assert verdict.attributed_paise == 50000


def test_uncoverable_gap_resolves_as_chargeback_without_the_model():
    evidence = {
        "gap_paise": -455762,
        "exact_match": None,
        "pair_match": None,
        "candidate_refunds": [],
        "gap_remaining_after_all_candidates": 455762,
    }
    verdict = resolve_deterministically(evidence)

    assert verdict is not None
    assert verdict.primary_cause == Cause.CHARGEBACK
    assert verdict.attributed_paise == 455762


def test_ambiguous_gap_is_left_for_the_model():
    evidence = {
        "gap_paise": -140000,
        "exact_match": None,
        "pair_match": None,
        "candidate_refunds": [{"refund_id": "RFD_1", "amount_paise": 90000}],
        "gap_remaining_after_all_candidates": 50000,
    }
    assert resolve_deterministically(evidence) is None