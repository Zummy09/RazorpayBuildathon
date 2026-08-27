"""Classifies one unexplained settlement gap.

This is the only place in the system where an LLM is used. It receives
facts assembled by evidence.py and decides which explanation fits. It
never performs arithmetic -- amount matches are given to it as findings.
"""

import json
import os

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import ValidationError

from src.models import Cause, ExceptionVerdict

import hashlib
from pathlib import Path

load_dotenv()

MODEL = "gemini-3.6-flash"
CONFIDENCE_THRESHOLD = 0.85
MAX_ATTEMPTS = 2

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

rounding
  Sub-rupee drift from fees and GST being rounded per transaction. Only
  applies to very small gaps, under a few rupees.

unknown
  None of the above fits the evidence. Use this whenever no candidate
  plausibly explains the gap. Do not force a category.

RULES

- Do not perform arithmetic. exact_match and pair_match are findings
  computed deterministically and given to you as facts.
- If exact_match and pair_match are both null and no candidate is
  clearly plausible, return unknown with low confidence.
- Confidence must reflect the strength of the evidence. An exact amount
  match with a long lag is high confidence. A candidate that merely
  exists is not.
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
    """Return a verdict for one gap. Never raises -- failures become
    an unknown verdict so a bad response cannot kill the batch."""
    last_error = None

    for attempt in range(MAX_ATTEMPTS):
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