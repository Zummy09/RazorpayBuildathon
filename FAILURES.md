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