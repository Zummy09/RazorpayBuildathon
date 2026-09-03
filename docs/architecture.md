## Where the AI is, and where it is not

Python does all arithmetic and all matching:

- grouping payments into settlement batches by capture date
- computing platform fee and GST per transaction
- summing gross, deductions and justifiable refunds
- comparing the rebuilt figure against the bank credit
- searching candidate refunds for exact and pairwise amount matches
- computing how much of a gap survives the best candidate, and all
  candidates summed

All of it is exact, free, and identical on every run.

The model does one thing: name the cause of a gap it is handed. It
receives the computed gap, the filtered candidates, and the amount-match
findings as facts. It never adds anything up.

> The model classifies. It never calculates.

### Cases that never reach the model

Two classes of exception are resolved in code.

**A single candidate matching the gap exactly.** Not ambiguous. Calling
a model to confirm arithmetic that has already been performed is waste.

**A gap no candidate covers, alone or summed.** If every candidate
refund added together leaves a large remainder, part of that gap has no
record in the merchant's data — which is the definition of a chargeback.
This is a threshold on a computed number, not a judgment.

The second rule was added after four prompt revisions failed to make the
model emit a `chargeback` label. Confidence rose from 0.3 to 0.8 across
those attempts and the reasoning named chargebacks explicitly, but the
model would not commit to a cause it could not verify from the data.
That reluctance is arguably correct behaviour, and the right response
was to recognise that the question was not ambiguous in the first place.

### What the model is actually for

Gaps with more than one cause. A settlement where a refund explains part
of the shortfall and the remainder has no record anywhere cannot be
attributed by any single rule. On those cases the model returns low
confidence rather than forcing a category — which is the behaviour the
confidence gate exists to act on.

## The confidence gate

Three outcomes, not two.

    cause == unknown        -> unresolvable
    confidence < 0.85       -> escalated for human review
    confidence >= 0.85      -> auto-resolved

`unknown` is checked before confidence. A model stating that none of the
available categories fit is making a claim about the taxonomy, not
expressing uncertainty. Collapsing the two loses that signal.

The threshold leans toward escalation deliberately. Auto-resolving a
wrong verdict writes a silent error into the books that surfaces at
audit. Escalating a correct verdict costs a reviewer two minutes. The
errors are not symmetric and the threshold should not be either.

## Data design

30 days of synthetic activity: ~1,380 payments, ~67 refunds, 6
chargebacks, 30 settlements. Generated from a fixed seed so a reviewer
running the repo reproduces the reported numbers exactly.

Three sources of difficulty are planted deliberately:

**Timing.** Payments settle T+2, so any settlement pays for transactions
captured two days earlier. Matching by date fails on every settlement,
not as an edge case.

**Old-cycle refunds.** Ten refunds are raised 15-25 days after their
payment already settled. Each produces a deduction with no corresponding
payment in the current batch.

**Chargebacks.** Six payments are reversed by the customer's bank.
These are deducted from settlements but never written to
`refunds.csv` or anywhere else the reconciler can read. Their absence
from the merchant's records is the point — it is what makes them
unexplainable from those records alone.

### Ground truth

Every planted problem is recorded in `data/ground_truth.csv` at the
moment it is created, with the settlement date it will surface on, the
cause, the amount, and the record that caused it.

Only `evaluate.py` reads that file. The reconciler and classifier never
see it. The separation is physical rather than conventional, because an
accuracy number produced by a system with access to its own answer key
is worthless.

## Failure handling

The classifier never raises. A call is attempted twice — the second with
an instruction that the previous response was malformed — and if both
fail it returns a verdict of `unknown` at confidence 0.0, with the
underlying exception preserved in the reasoning field.

The consequence is that a classification failure becomes one unresolved
exception on the report rather than a dead batch. This was verified
under a real outage rather than an injected one: the model endpoint was
retired mid-development, and later the API quota was exhausted. In both
cases the pipeline completed, produced a full audit trail, resolved
every deterministic case correctly, and listed the unclassified gaps
with the reason attached.

### The cost of that design

Broad exception handling means programming errors surface as API
failures. An unused `os.path` import shadowed a local variable and the
resulting `NameError` was reported as `api call failed: module 'ntpath'
has no attribute 'read_text'`.

The free-text reasoning field is what makes this recoverable. A
structured verdict alone would have shown only `cause=unknown`; the
reasoning carried the actual exception text and pointed at the fault.
Capturing model reasoning alongside a structured answer is worth the
tokens for exactly this reason.

### Input validation

`loader.py` validates every row against its Pydantic model on read.
Malformed rows are collected rather than raised, so a bad row appears on
the report as a data-quality exception instead of killing a 1,380-row
load.

## Known limitations

**The model does not produce partial attributions.** The verdict schema
holds a list of causes with an attributed amount each, and routing
escalates anything covering less than 90% of the gap. The mechanism is
tested and works. But across 8 classifications the model returned a
single cause every time, attributing the full gap to it — including on
a settlement that ground truth records as two chargebacks plus a refund.
Coverage is therefore always 100% and the gate never fires. Permitting
an answer is not the same as eliciting it; the prompt needs to make
partial attribution the expected output. See F-12.

**Old-cycle refunds are full-value.** The gap therefore matches a
historical refund exactly, or matches a pair. Real old-cycle refunds are
frequently partial, which would require fuzzy matching over a date
window rather than exact matching. This is the first extension.

**Batch membership is tested on an exact capture date.** A refund whose
payment was captured one day outside the batch is treated as
unexplainable. A production reconciler would search a lookback window.
Widening this introduces a window-size parameter that needs tuning
against measured accuracy, which was not possible in the time available.

**Combination search stops at pairs.** Triples were rejected on
statistical grounds rather than cost: with a dozen candidates, three
amounts summing to a gap by coincidence becomes likely enough to produce
false matches.

**Rounding drift does not appear in this dataset.** The reconciler
applies the same integer fee calculation as the generator, so the
rounding cancels exactly. A real merchant's fee model would differ
slightly from the gateway's, producing sub-rupee drift. The tolerance
band exists for that case and is currently set to zero.

**No held-out split.** Accuracy is measured on the full dataset. With a
larger generated corpus the correct approach is to tune on one split and
report on another.

**Single settlement cycle.** Split settlements, rolling reserve, instant
settlement and partial capture are all real and all unmodelled.

## What is deliberately not used

**LangGraph or an agent runtime.** The control flow is static: every
settlement takes the same path and the only branch is a numeric
threshold. A graph runtime would add a dependency and a layer of
indirection without enabling anything the pipeline cannot already do.

**A vector database.** There is no retrieval problem. Candidate refunds
are selected by date range and payment lineage — a lookup, not a
similarity search.

**A web interface.** The deliverable is a measured reconciliation run.

## Development record

Every runtime failure found while building this is recorded in
[FAILURES.md](../FAILURES.md), including the ones that took hours and
the wrong theories pursued along the way.

The most instructive: the classifier would not emit a `chargeback`
label across four prompt revisions. The model stated the reason in its
own first response — that the schema permitted only three causes — and
it was read as hedging. `models.py` contained three `class Cause`
definitions, accumulated by appending rather than editing.
`print(Cause)` showed four values because Python binds the last
definition to the name, but `ExceptionVerdict` had captured an earlier
three-value enum at its own definition point. Roughly four hours and
eight API calls were spent on a prompt problem that was a file hygiene
problem.

