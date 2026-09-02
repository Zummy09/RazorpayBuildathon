"""Loads the CSV files into validated objects.

Rows that fail validation are collected rather than raised, so a bad
row lands on the exception list instead of killing the run.
"""

import csv

from src.models import Payment, Refund, Settlement


def _load(path: str, model) -> tuple[list, list[dict]]:
    good, bad = [], []
    with open(path, newline="", encoding="utf-8") as f:
        for i, row in enumerate(csv.DictReader(f), start=2):
            try:
                good.append(model(**row))
            except Exception as e:
                bad.append({"file": path, "line": i, "row": row, "error": str(e)})
    return good, bad


def load_all(data_dir: str = "data") -> tuple[list, list, list, list[dict]]:
    payments, bad_p = _load(f"{data_dir}/payments.csv", Payment)
    refunds, bad_r = _load(f"{data_dir}/refunds.csv", Refund)
    settlements, bad_s = _load(f"{data_dir}/settlements.csv", Settlement)
    return payments, refunds, settlements, bad_p + bad_r + bad_s