from src.models import Cause, ExceptionVerdict, Route
from src.pipeline import resolve_deterministically, route_verdict


def _verdict(cause, confidence):
    return ExceptionVerdict(
        cause=cause,
        confidence=confidence,
        reasoning="test",
        evidence_refund_ids=[],
        suggested_action="test",
    )


def test_high_confidence_auto_resolves():
    v = _verdict(Cause.OLD_CYCLE_REFUND, 0.95)
    assert route_verdict(v) == Route.AUTO_RESOLVED


def test_low_confidence_escalates():
    v = _verdict(Cause.OLD_CYCLE_REFUND, 0.40)
    assert route_verdict(v) == Route.ESCALATED


def test_unknown_is_unresolvable_regardless_of_confidence():
    """Unknown is a claim about the taxonomy, not an expression of
    uncertainty. It is checked before the threshold."""
    v = _verdict(Cause.UNKNOWN, 0.95)
    assert route_verdict(v) == Route.UNRESOLVABLE


def test_single_exact_match_resolves_without_the_model():
    evidence = {
        "exact_match": "RFD_0001",
        "pair_match": None,
        "candidate_refunds": [{"refund_id": "RFD_0001", "amount_paise": 50000}],
        "gap_remaining_after_all_candidates": 0,
    }
    verdict = resolve_deterministically(evidence)

    assert verdict is not None
    assert verdict.cause == Cause.OLD_CYCLE_REFUND
    assert verdict.confidence == 1.0


def test_uncoverable_gap_resolves_as_chargeback_without_the_model():
    """No refund covers this gap, alone or summed. That is arithmetic,
    not judgment -- the model is not consulted."""
    evidence = {
        "exact_match": None,
        "pair_match": None,
        "candidate_refunds": [],
        "gap_remaining_after_all_candidates": 455762,
    }
    verdict = resolve_deterministically(evidence)

    assert verdict is not None
    assert verdict.cause == Cause.CHARGEBACK


def test_ambiguous_gap_is_left_for_the_model():
    """A candidate exists but does not cover the gap. This is the case
    the classifier is for."""
    evidence = {
        "exact_match": None,
        "pair_match": None,
        "candidate_refunds": [{"refund_id": "RFD_1", "amount_paise": 90000}],
        "gap_remaining_after_all_candidates": 50000,
    }
    assert resolve_deterministically(evidence) is None