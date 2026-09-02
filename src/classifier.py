"""Classifies one unexplained settlement gap.

This is the only place in the system where an LLM is used. It receives
facts assembled by evidence.py and decides which explanation fits. It
never performs arithmetic -- amount matches are given to it as findings.
"""

import json
import os
import time
import logging

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import ValidationError

from src.models import Cause, ExceptionVerdict

import hashlib
from pathlib import Path

load_dotenv()

# the google-genai SDK logs an AFC advisory on every generate_content
# call. we are not using function calling, so it is noise.
logging.getLogger("google_genai").setLevel(logging.ERROR)

MODEL = "gemini-3.6-flash"
CONFIDENCE_THRESHOLD = 0.85
MAX_ATTEMPTS = 2

MIN_CALL_INTERVAL = 13.0   # seconds; free tier is 5 rpm
_last_call_at  = 0.0

_client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])


SYSTEM_PROMPT = """You classify unexplained gaps in payment gateway settlements.

A merchant receives one net bank credit per settlement cycle. A
deterministic reconciler rebuilds what that credit should have been from
the merchant's own records. When the rebuilt figure does not match the
bank credit, the difference is an unexplained gap and you are asked why.

CAUSES

old_cycle_refund
  A refund was deducted from this settlement, but its original payment
  settled in an earlier cycle. The reconciler could not account for it
  because the payment is not in this settlement's batch. Identified by
  a candidate refund whose days_since_payment is well above the
  settlement lag, and whose amount matches the gap either alone or in
  combination.

chargeback
  The customer's bank reversed a payment directly. The merchant has no
  record of it -- chargebacks never appear in the refund data. Identified
  by a gap that no candidate refund explains. The strongest signal is
  gap_remaining_after_all_candidates: if that value is large and positive,
  part of the gap cannot be a refund at all, because even every candidate
  summed together does not cover it.

  A chargeback requires NO supporting refund evidence. Absence of any
  candidate refund, combined with a gap too large for rounding, IS the
  evidence. Do not return unknown merely because there is no refund to
  point at -- that is precisely what a chargeback looks like.

  A chargeback is never confirmable from merchant records -- that is
  what defines it. Unconfirmability is not a reason to return unknown.
  If the gap has no refund explanation and is too large for rounding,
  the cause IS chargeback. Say so.

rounding
  Sub-rupee drift from fees and GST being rounded per transaction. Only
  applies to very small gaps, under a few rupees.

unknown
  The evidence is genuinely ambiguous -- for example a gap that is
  partially explained by a refund with a remainder you cannot attribute
  with confidence. Do not use unknown when the evidence clearly fits a
  category above.

RULES

- Do not perform arithmetic. exact_match, pair_match, and the remainder
  figures are computed deterministically and given to you as facts.
- A gap may have more than one cause. If a candidate refund explains only
  part of it, report the cause with the strongest evidence, state the
  unexplained remainder in your reasoning, and lower your confidence to
  reflect the partial explanation.
- If exact_match and pair_match are both null and
  gap_remaining_after_all_candidates is large, the gap contains money that
  has no record in the merchant's data. That points to chargeback.
- Confidence must reflect the strength of the evidence. An exact amount
  match with a long lag is high confidence. A partially explained gap is
  not. A gap you cannot attribute is low confidence or unknown.
- evidence_refund_ids must list only refunds you actually relied on.
  Leave it empty if you relied on none.
- suggested_action is one short line describing what a finance operator
  should do next.
"""


def _build_prompt(evidence: dict, strict: bool = False) -> str:
    parts = [
        "Classify this settlement gap.",
        "",
        json.dumps(evidence, indent=2),
    ]
    if strict:
        parts.append(
            "\nYour previous response did not conform to the schema. "
            "Return only valid JSON matching the required structure."
        )
    return "\n".join(parts)



def _call_model(evidence: dict) -> ExceptionVerdict:
    """One classification. Retries once on a bad response, then degrades
    to an unknown verdict so a single failure cannot kill the batch."""
    global _last_call_at
    last_error = None

    for attempt in range(MAX_ATTEMPTS):
        # free tier is 5 requests per minute -- space the calls out
        wait = MIN_CALL_INTERVAL - (time.time() - _last_call_at)
        if wait > 0:
            time.sleep(wait)
        _last_call_at = time.time()

        try:
            response = _client.models.generate_content(
                model=MODEL,
                contents=_build_prompt(evidence, strict=attempt > 0),
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    response_schema=ExceptionVerdict,
                    temperature=0.0,
                ),
            )
            return ExceptionVerdict.model_validate_json(response.text)

        except ValidationError as e:
            last_error = f"schema validation failed: {e}"
        except Exception as e:
            last_error = f"api call failed: {e}"

    return ExceptionVerdict(
        cause=Cause.UNKNOWN,
        confidence=0.0,
        reasoning=f"Classification failed after {MAX_ATTEMPTS} attempts. {last_error}",
        evidence_refund_ids=[],
        suggested_action="Escalate to a human reviewer.",
    )

CACHE_DIR = Path(".cache/verdicts")


def _cache_key(evidence: dict) -> str:
    """A short stable id for this exact evidence package."""
    blob = json.dumps(evidence, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def classify(evidence: dict, use_cache: bool = True) -> ExceptionVerdict:
    """Classify a gap, reusing a saved verdict when the evidence is identical.

    Safe because the model runs at temperature 0 -- the same evidence
    always produces the same verdict.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{_cache_key(evidence)}.json"

    if use_cache and path.exists():
        return ExceptionVerdict.model_validate_json(path.read_text())

    verdict = _call_model(evidence)

    # never cache a failure -- a quota error would be frozen forever
    if verdict.confidence > 0:
        path.write_text(verdict.model_dump_json(indent=2))

    return verdict