# Failure Journal

Runtime failures found while building this system, what caused them,
and how the system changed as a result.

Logged only when the fix changed the design or added a guardrail.
Typos and environment setup are not failures.

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

## F-07 — Model could not return a cause that was not in the schema

**Symptom**
Chargeback settlements returned cause=unknown while the reasoning field
explicitly named a chargeback. Two rounds of prompt revision raised
confidence from 0.1 to 0.85 but never changed the label.

**Root cause**
CHARGEBACK was added to the prompt but never to the Cause enum. Since
the classifier uses structured output, the enum is sent to the model as
a schema constraint — the model was physically unable to emit a value
the schema did not permit, and correctly fell back to unknown.

**What I tried**
Assumed the prompt was ambiguous and revised it twice, reordering the
cause list and adding explicit instructions. Both were wrong. The model
eventually stated the reason itself: "the schema constraints restrict
cause to old_cycle_refund, rounding, or unknown."

**Fix**
Added CHARGEBACK to the enum. The prompt was already correct.

**What this showed**
Structured output is a hard constraint, not a suggestion — which is why
it is worth using, and why the prompt and the schema must be changed
together. The free-text reasoning field is what made this diagnosable:
without it, this would have looked like model uncertainty rather than a
schema mismatch, and I would have kept editing the prompt.

**Cost**
~60 min across two wrong prompt revisions.

**Second cause found**
After fixing the enum, the model still returned unknown. The CAUSES
section stated three times that unconfirmability is not grounds for
abstaining, but a general rule further down the prompt read "a gap you
cannot attribute is low confidence or unknown." The model followed the
later, more general instruction. Contradictions between a specific
definition and a general rule resolve in favour of whatever the model
reads last.

**Third round**
Two prompt revisions appeared to have no effect. A string check on the
assembled prompt showed the contradicting rule had never been removed —
the fix had been added alongside it rather than replacing it. Asserting
on the prompt text costs nothing and would have caught this two API
calls earlier.


## F-08 — Two copies of the project, edits landing in the wrong one

**Symptom**
Four prompt revisions failed to make the classifier return `chargeback`.
The model's own reasoning said the schema only permitted three causes,
yet a direct check on the enum printed four.

**Root cause**
Two copies of the project existed — one on C:\Users\Admin\Desktop and
one on D:\. The venv resolved to D:, so imports loaded a stale
`models.py` without CHARGEBACK. Edits were being made in one tree and
executed from another.

**What I tried**
Assumed prompt ambiguity and revised the prompt four times, spending
several API calls. Added a string assertion on the prompt, which found
one real bug but not this one. Only a Pydantic ValidationError — raised
by the deterministic path, which does not go near the model — exposed
that the enum being validated against was not the enum on disk.

**Fix**
Removed the duplicate tree and confirmed `src.models.__file__` resolves
to the working copy.

**What this showed**
The model was reporting the truth the entire time. "The schema
restricts cause to three values" was accurate — I assumed it was
hedging. Printing a value proves what a name holds; printing
`module.__file__` proves which file that name came from.

**Cost**
~4 hours and roughly 8 API calls chasing a prompt problem that was an
environment problem.

## F-09 — Cache write crashed on a rupee symbol

**Symptom**
UnicodeEncodeError mid-run: 'charmap' codec can't encode '\u20b9'. The
classification had succeeded; the crash was writing the verdict to cache.

**Root cause**
Windows defaults file encoding to cp1252, which has no rupee symbol. The
model included one in its reasoning text.

**Fix**
Explicit encoding="utf-8" on every file read and write.

**What this showed**
The default would not have failed on Linux or macOS, so this was a
platform-specific crash that a reviewer running the repo elsewhere would
never see — and I would never have seen a bug they hit.

**Cost**
~10 min, plus the API calls lost from the aborted run.