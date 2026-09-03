"""Scores the pipeline against ground truth.

Ground truth is read ONLY here. No other module may import it.
"""

import csv
from collections import defaultdict

from src.models import ReconStatus, Route


def load_ground_truth(path: str = "data/ground_truth.csv") -> dict:
    """Planted exceptions, keyed by the date they should surface on."""
    truth = defaultdict(list)
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            truth[row["settled_on"]].append(row)
    return dict(truth)


def evaluate(results, records, truth: dict) -> dict:
    expected_dates = set(truth)
    flagged_dates = {
        str(r.settled_on) for r in results if r.status == ReconStatus.EXCEPTION
    }

    true_positives = flagged_dates & expected_dates
    false_positives = flagged_dates - expected_dates
    false_negatives = expected_dates - flagged_dates

    precision = len(true_positives) / len(flagged_dates) if flagged_dates else 0.0
    recall = len(true_positives) / len(expected_dates) if expected_dates else 0.0

    # classification: was the cause right, and were the right refunds cited?
    correct_cause = 0
    correct_evidence = 0
    scored = 0

    multi_cause_dates = []

    for rec in records:
        date_key = str(rec.settled_on)
        if date_key not in truth:
            continue

        scored += 1
        rows = truth[date_key]
        expected_causes = {row["cause"] for row in rows}

        if len(expected_causes) > 1:
            multi_cause_dates.append(date_key)

        # a gap may contain more than one cause; the verdict schema holds
        # only one, so any real cause counts as correct
        if rec.cause.value in expected_causes:
            correct_cause += 1

        # chargebacks are never written to the merchant's data, so the
        # system cannot cite an id for them. citing nothing is correct.
        if rec.cause.value == "chargeback":
            if not rec.evidence_refund_ids:
                correct_evidence += 1
        else:
            expected_refunds = {
                row["caused_by"]
                for row in rows
                if not row["caused_by"].startswith("CBK_")
            }
            if set(rec.evidence_refund_ids) == expected_refunds:
                correct_evidence += 1

    by_route = defaultdict(lambda: {"count": 0, "paise": 0})
    for rec in records:
        by_route[rec.route]["count"] += 1
        by_route[rec.route]["paise"] += abs(rec.gap_paise)

    matched = sum(1 for r in results if r.status == ReconStatus.MATCHED)

    return {
        "settlements": len(results),
        "matched": matched,
        "match_rate": matched / len(results),
        "exceptions": len(records),
        "expected_exceptions": len(expected_dates),
        "true_positives": sorted(true_positives),
        "false_positives": sorted(false_positives),
        "false_negatives": sorted(false_negatives),
        "precision": precision,
        "recall": recall,
        "scored": scored,
        "correct_cause": correct_cause,
        "correct_evidence": correct_evidence,
        "by_route": dict(by_route),
        "llm_calls": sum(1 for r in records if r.resolved_by == "llm"),
        "multi_cause_dates": multi_cause_dates,
    }