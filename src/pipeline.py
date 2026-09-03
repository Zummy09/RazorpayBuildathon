"""End-to-end run: load, reconcile, explain, route, report.

Deterministic code does all matching and arithmetic. The classifier is
called only when amount matching is ambiguous.
"""

from src.models import (
    Cause,
    ExceptionRecord,
    ExceptionVerdict,
    ReconStatus,
    Route,
)
from src.loader import load_all
from src.reconciler import reconcile_all
from src.evidence import build_evidence
from src.classifier import classify, CONFIDENCE_THRESHOLD
from src.models import Cause, CauseAttribution, ExceptionVerdict


COVERAGE_THRESHOLD = 0.9


def route_verdict(verdict: ExceptionVerdict, gap_paise: int) -> Route:
    """Coverage and confidence are separate tests. A verdict that explains
    only part of a gap escalates however certain the model claims to be."""
    if not verdict.causes:
        return Route.UNRESOLVABLE

    if verdict.primary_cause == Cause.UNKNOWN:
        return Route.UNRESOLVABLE

    coverage = verdict.attributed_paise / abs(gap_paise) if gap_paise else 0.0

    if coverage < COVERAGE_THRESHOLD:
        return Route.ESCALATED

    if verdict.confidence < CONFIDENCE_THRESHOLD:
        return Route.ESCALATED

    return Route.AUTO_RESOLVED


def resolve_deterministically(evidence: dict) -> ExceptionVerdict | None:
    """Cases where arithmetic already answers the question."""
    gap = abs(evidence["gap_paise"])

    if (
        evidence["exact_match"] is None
        and evidence["pair_match"] is None
        and evidence["gap_remaining_after_all_candidates"] > 100_000
    ):
        remainder = evidence["gap_remaining_after_all_candidates"]
        return ExceptionVerdict(
            causes=[
                CauseAttribution(
                    cause=Cause.CHARGEBACK,
                    amount_paise=remainder,
                    evidence_refund_ids=[],
                )
            ],
            confidence=0.95,
            reasoning=(
                f"No candidate refund covers this gap. All candidates summed "
                f"leave Rs {remainder / 100:,.2f} unaccounted for, so part of "
                f"the gap has no record in the merchant's data."
            ),
            suggested_action="Request the chargeback report from the gateway.",
        )

    if evidence["exact_match"] and len(evidence["candidate_refunds"]) == 1:
        refund_id = evidence["exact_match"]
        return ExceptionVerdict(
            causes=[
                CauseAttribution(
                    cause=Cause.OLD_CYCLE_REFUND,
                    amount_paise=gap,
                    evidence_refund_ids=[refund_id],
                )
            ],
            confidence=1.0,
            reasoning=(
                f"Single candidate {refund_id} matches the gap exactly and "
                f"its payment settled in an earlier cycle."
            ),
            suggested_action=f"Post {refund_id} against this settlement.",
        )

    return None


def run(data_dir: str = "data"):
    payments, refunds, settlements, bad_rows = load_all(data_dir)
    results = reconcile_all(payments, refunds, settlements)

    records = []
    for r in results:
        if r.status != ReconStatus.EXCEPTION:
            continue

        evidence = build_evidence(r, payments, refunds)

        verdict = resolve_deterministically(evidence)
        resolved_by = "deterministic"
        if verdict is None:
            verdict = classify(evidence)
            resolved_by = "llm"

        gap = abs(r.gap_paise)
        coverage = verdict.attributed_paise / gap if gap else 0.0

        records.append(
            ExceptionRecord(
                settlement_id=r.settlement_id,
                settled_on=r.settled_on,
                gap_paise=r.gap_paise,
                route=route_verdict(verdict, r.gap_paise),
                cause=verdict.primary_cause,
                causes=verdict.causes,
                coverage=coverage,
                confidence=verdict.confidence,
                evidence_refund_ids=verdict.all_evidence_ids,
                reasoning=verdict.reasoning,
                resolved_by=resolved_by,
            )
        )

    return results, records, bad_rows


def _rupees(paise: int) -> str:
    return f"Rs {paise / 100:,.2f}"


def print_report(results, records, bad_rows):
    matched = [r for r in results if r.status == ReconStatus.MATCHED]
    settled_total = sum(r.actual_paise for r in results)

    print("=" * 64)
    print("SETTLEMENT RECONCILIATION")
    print("=" * 64)
    print(f"settlements       {len(results)}")
    print(f"matched           {len(matched)}  "
          f"({len(matched) / len(results):.0%})")
    print(f"exceptions        {len(records)}")
    print(f"settled value     {_rupees(settled_total)}")

    if bad_rows:
        print(f"\nrejected rows     {len(bad_rows)}")
        for b in bad_rows[:5]:
            print(f"  {b['file']} line {b['line']}: {b['error'][:70]}")

    by_route = {route: [] for route in Route}
    for rec in records:
        by_route[rec.route].append(rec)

    print("\n" + "-" * 64)
    print("EXCEPTION ROUTING")
    print("-" * 64)
    for route in Route:
        rows = by_route[route]
        value = sum(abs(r.gap_paise) for r in rows)
        print(f"{route.value:<16} {len(rows):>3}   {_rupees(value):>16}")

    llm_calls = sum(1 for r in records if r.resolved_by == "llm")
    print(f"\nmodel calls       {llm_calls} of {len(records)} exceptions")

    print("\n" + "-" * 64)
    print("EXCEPTION DETAIL")
    print("-" * 64)
    for rec in sorted(records, key=lambda r: abs(r.gap_paise), reverse=True):
        print(f"\n{rec.settlement_id}  {rec.settled_on}  "
              f"{_rupees(rec.gap_paise)}")
        print(f"  route      {rec.route.value}  "
              f"({rec.resolved_by}, confidence {rec.confidence})")
        print(f"  coverage   {rec.coverage:.0%}")
        print(f"  cause      {rec.cause.value}")
        if len(rec.causes) > 1:
            for c in rec.causes:
                print(f"    {c.cause.value:20} {_rupees(c.amount_paise)}")
        print(f"  evidence   {', '.join(rec.evidence_refund_ids) or 'none'}")
        print(f"  reasoning  {rec.reasoning}")


if __name__ == "__main__":
    print_report(*run())