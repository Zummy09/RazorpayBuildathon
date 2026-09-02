# Failure Journal

Runtime failures found while building this system, what caused them,
and how the system changed as a result.

Logged only when the fix changed the design or added a guardrail.
Typos and environment setup are not failures.

---


| ID | Failure | Category |
|---|---|---|
| F-01 | Settlements inflated by failed payments | Data correctness |
| F-02 | Set membership on unhashable Pydantic objects | Language |
| F-03 | Reconciler replayed the generator's own logic | Design |
| F-04 | Normal refunds misclassified as exceptions | Data consistency |
| F-05 | Model endpoint retired mid-build | External |
| F-06 | Pipeline ran against stale CSVs | Environment |
| F-07 | Contradicting rule cancelled a prompt definition | Prompt |
| F-08 | Duplicate class definitions shadowing an enum | Code hygiene |
| F-09 | Encoding crash, then a poisoned cache | Platform |
| F-10 | Error handling masked a code bug as an API failure | Design |


---

## F-01 — Settlements inflated by failed payments

**Symptom**
Settlement totals exceeded actual captured payments by ₹7,39,529
across 30 settlements. Every settlement was wrong, not just some.

**Root cause**
`build_settlements` grouped payments by capture date but never filtered
on status. All 101 failed payments were included in gross — and fees
were deducted on them too, which never happens in reality since no
money moved.

**What I tried**
Checked the fee calculation first, assuming a rounding error. Wrong
track. Then compared settlement total against captured-only gross and
saw the gap was roughly 101 × average payment value, which pointed
straight at the status field.

**Fix**
Filter each batch to `status == CAPTURED` before summing.

**Cost**
~40 minutes. Would have silently corrupted every match rate downstream.

---

## F-03 — Reconciler matched 30/30 by replaying the generator's own logic

**Symptom**
Every settlement reconciled to exactly ₹0.00 gap. Zero exceptions,
despite 10 planted old-cycle refunds in ground truth.

**Root cause**
The reconciler subtracted refunds by settlement date — the identical
rule the generator used to build the settlements. Two components
applying the same rule to the same data can never disagree, so the
reconciler was replaying the generator's arithmetic rather than
independently verifying it.

**What I tried**
Assumed the refunds weren't reaching the settlements. Traced one
ground-truth refund end to end and found it WAS being counted — which
was the real problem, not the absence I expected.

**Fix**
Restricted the reconciler to what a real merchant actually knows. It
no longer assumes which refunds belong to which settlement; it only
subtracts a refund when the original payment is in that settlement's
batch. Old-cycle refunds now produce genuine unexplained gaps.

**Cost**
~2 hour. This was a design error, not a coding error — the reconciler
had access to information a real merchant would never have.

## F-04 — Normal refunds misclassified as exceptions

**Symptom**
20 exceptions instead of the 10 in ground truth. Unexplained gaps of
up to ₹23,000 — larger than any single payment in the dataset.

**Root cause**
Normal refunds were generated with a 1-2 day lag, but settlements run
T+2. A refund created 1 day after its payment lands on a settlement
whose batch is payments from the day BEFORE that payment. The
reconciler correctly found the payment outside the batch and refused
to subtract it — so 26 legitimate refunds were flagged as unexplained
and stacked onto the same settlements.

**What I tried**
Read the oversized gaps as a reconciler bug first. Traced the lag
against batch membership and found perfect correlation: all 26 lag-1
refunds fell outside their batch, all 33 lag-2 refunds fell inside.
The reconciler was correct; the data was inconsistent with the
settlement cycle.

**Fix**
Refunds now settle T+2 like payments. Exceptions dropped from 20 to 10,
matching ground truth exactly.

**Known limitation**
Exact-date batch matching is brittle. A real reconciler would search a
lookback window rather than requiring an exact capture date. Deferred
until metrics exist to tune the window against.

**Cost**
~45 min. The oversized gaps were the tell — a gap can never exceed the
largest single payment unless multiple items are being missed.


## F-05 — Model endpoint retired mid-build

**Symptom**
Every classification returned cause=unknown, confidence=0.0. No crash,
no stack trace — the batch completed and the failures appeared on the
exception list.

**Root cause**
404 NOT_FOUND: gemini-2.0-flash was retired. The model identifier was
hardcoded from documentation that had since moved on.

**What I tried**
Nothing — the error was already in the verdict's reasoning field,
because the fallback path records the underlying exception rather than
discarding it.

**Fix**
Updated the model identifier. Model choice is a single constant in
classifier.py, so provider or version changes are a one-line edit.

**What this proved**
The retry-then-degrade path works under a real failure that was not
injected deliberately. A total API outage costs the run its
classifications but not its results — every unclassified gap surfaces
as an honest exception rather than a crash.

**Cost**
~5 min to fix. Worth more as evidence than it cost.


## F-06 — Pipeline ran against stale CSVs

**Symptom**
The in-memory run produced 9 exceptions. Running the same logic
against data/*.csv produced 20, with several settlements reporting
zero candidate refunds despite large gaps.

**Root cause**
The CSV files on disk were written before the F-04 fix to refund
lag. The generator and the committed data had drifted apart, so the
pipeline was reconciling a dataset that no longer matched the code
that produced it.

**What I tried**
Read the zero-candidate settlements as an evidence-builder bug.
Compared record counts between the disk load and an in-memory
generation and found the refund count differed.

**Fix**
Regenerated the data. README now states that generate must run before
pipeline, and the two are separate commands by design — the pipeline
consumes data as an external input rather than producing it.

**Cost**
~20 min. The tell was 20 exceptions, the same count as the F-04
symptom — the old data still carried the old bug.

## F-07 — Model identified chargebacks but refused to label them

**Symptom**
Three settlements returned cause=unknown while the reasoning field
explicitly said "indicates a customer bank chargeback." Confidence rose
from 0.1-0.3 to 0.85 after a prompt revision, but the cause field did
not change.

**Root cause**
The prompt defined chargebacks as identifiable by the absence of refund
evidence, while also instructing the model to return unknown when it
could not confirm a cause from the data. For a chargeback these are the
same condition -- unconfirmability from merchant records is the
defining feature, not a reason to abstain.

**Fix**
Stated explicitly that unconfirmability is not grounds for unknown, and
reordered the cause list so chargeback is read last.

**What this showed**
The reasoning field was worth more than the label. Without it, this
would have looked like model uncertainty rather than a contradiction in
the prompt. Capturing free-text reasoning alongside a structured verdict
is what made it diagnosable.

---

## F-07 — Model would not emit a label the prompt had defined

**Symptom**
Chargeback settlements returned `cause=unknown` while the reasoning
field explicitly named a chargeback. Four prompt revisions raised
confidence from 0.1 to 0.8; the label never changed.

**What I tried**
Revised the chargeback definition. Reordered the cause list. Added
explicit instructions that unconfirmability was not grounds for
abstaining. Each attempt cost an API call and each appeared to fail.

Then added a string assertion on the assembled prompt rather than
assuming the edits had landed:

    print("bad rule removed:", "low confidence or unknown" not in SYSTEM_PROMPT)

It printed `False`. A general rule further down the prompt still read
"a gap you cannot attribute is low confidence or unknown" — directly
contradicting the chargeback definition forty lines above it. The rules
section came last, so it won.

**Fix**
Removed the contradicting sentence.

**What this showed**
Later instructions override earlier ones. A specific definition can be
cancelled by a general rule the model reads afterwards. And asserting on
the assembled prompt costs nothing, while assuming an edit landed cost
two API calls.

**Cost**
~1 hour, 4 API calls.

---

## F-08 — Duplicate class definitions shadowing the enum

**Symptom**
After F-07, the model still would not return `chargeback`. Its very
first response had said: "the schema constraints restrict cause to
old_cycle_refund, rounding, or unknown." Printing `Cause` showed four
values including `chargeback`.

**What I tried**
Suspected a stale bytecode cache — cleared `__pycache__`, no change.
Suspected two project trees, since a second copy existed on another
drive — checked `src.models.__file__`, it resolved correctly. Checked
whether `Cause` was the same object in both modules — it was.

The break came from a `ValidationError` on the deterministic
chargeback path, which never touches the model:

    Input should be 'old_cycle_refund', 'rounding' or 'unknown'
    input_value=<Cause.CHARGEBACK: 'chargeback'>

Pydantic was rejecting a value from the same enum it was validating
against.

**Root cause**
`models.py` contained three `class Cause` and two `class
ExceptionVerdict` definitions, accumulated by pasting new code alongside
old rather than replacing it. Python binds the last definition to the
name, so `print(Cause)` showed four values — but `ExceptionVerdict` had
captured whichever `Cause` existed at its own definition point, which
had three.

**Fix**
Deduplicated `models.py` to one definition per class, ordered so `Cause`
precedes `ExceptionVerdict`.

**What this showed**
The model reported the fault accurately in its first response and it was
read as hedging. Printing a name shows the last binding, not the binding
a class captured when it was defined — so the check that felt conclusive
was the one that misled me. `model_json_schema()` would have shown the
truth immediately.

**Cost**
~4 hours, ~8 API calls, on a prompt problem that was a file hygiene
problem.

---

## F-09 — Cache write crashed on a rupee symbol, then poisoned itself

**Symptom**
`UnicodeEncodeError: 'charmap' codec can't encode character '\u20b9'`
mid-run. The classification had succeeded; the crash was writing the
verdict to cache.

On the next run, a different error: `Invalid JSON: EOF while parsing`.

**Root cause**
Two faults in sequence. Windows defaults file encoding to cp1252, which
has no rupee symbol, and the model had included one in its reasoning.
Then the crash left a zero-byte cache file behind, which the next run
tried to parse and died on.

**Fix**
Explicit `encoding="utf-8"` on every file read and write. The cache read
is now wrapped so a corrupt entry is deleted and refetched rather than
raising.

**What this showed**
The default would not have failed on Linux or macOS — this was a
platform-specific crash a reviewer running the repo elsewhere would
never hit, and one I would never have seen from their environment
either. And a cache that can crash the pipeline it exists to speed up is
worse than no cache.

**Cost**
~30 min plus the API calls lost from two aborted runs.

---

## F-10 — Error handling masked a code bug as an API failure

**Symptom**
Three settlements reported `api call failed: module 'ntpath' has no
attribute 'read_text'`. Read as an SDK or environment problem.

**Root cause**
Two unused imports — `from os import path` and `import os.path as path`
— shadowed the local `path` variable in the cache logic. The resulting
`NameError` was caught by the classifier's broad `except Exception` and
reported as an API failure.

Separately, an edit intended for `classify()` had been pasted into
`_call_model()`, replacing the response parsing with a cache read.

**Fix**
Removed the unused imports and restored the response parsing.

**What this showed**
The broad exception handler is what keeps one bad classification from
killing a batch, and it is also what disguised a `NameError` as a
network error. The trade-off is real. What made it recoverable was
preserving the exception text in the verdict's reasoning field — a
structured verdict alone would have shown only `cause=unknown`.

**Cost**
~30 min.