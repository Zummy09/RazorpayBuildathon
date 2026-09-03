# Settlement Reconciliation Agent

A merchant receives one lump-sum settlement from a payment gateway with
no breakdown. This agent reconstructs the settlement equation from the
merchant's own records, explains every rupee of the gap, and reports
what it could not resolve.

Built for the Razorpay AI Buildathon 2026 — Track 4, AI Finance Controller.

## The problem

A gateway does not pay per order. It batches a day's transactions,
subtracts what it is owed, and sends one bank credit:

      Gross captured payments
    − Platform fee and GST
    − Refunds settled this cycle
    − Chargebacks deducted
    ──────────────────────────
    = Net credit to the merchant

The merchant sees only the final number. Reconstructing the rest is the
problem this system solves.

It does not tie cleanly, for real reasons:

- **Timing.** Payments settle T+2, so a settlement pays for transactions
  from two days earlier, not today's.
- **Old-cycle refunds.** A refund raised weeks after its payment already
  settled is deducted now, with no matching payment in the current batch.
- **Chargebacks.** The customer's bank reverses a payment directly. The
  merchant has no record of it at all.

## Quickstart

    git clone https://github.com/Zummy09/RazorpayBuildathon
    cd RazorpayBuildathon
    python -m venv .venv
    .venv\Scripts\activate          # Windows
    source .venv/bin/activate       # macOS / Linux
    pip install -r requirements.txt

Add your API key to a `.env` file in the project root:

    GOOGLE_API_KEY=your_key_here

Generate the dataset, then run the reconciliation:

    python -m src.generate
    python -m src.pipeline

`generate` writes the CSV files. `pipeline` consumes them as external
input — the two are deliberately separate so the reconciler is never
handed data it just produced.

### Tests

    pytest

Twenty-four tests covering the deterministic core: fee and GST
arithmetic, T+2 batch selection, exclusion of failed payments, the
refund justification rule, candidate filtering, amount matching, and all
routing branches. No API calls required — the components that handle
money are verifiable without a model being available.

## Results

Measured on a 30-day synthetic dataset: 1,380 payments, 67 refunds,
6 chargebacks, 30 settlements. Ground truth is written by the generator
as each problem is planted, and read only by the evaluator.

| Metric | Value |
|---|---|
| Settlements processed | 30 |
| Reconciled cleanly | 18 (60%) |
| Exceptions raised | 12 |
| Exceptions in ground truth | 12 |
| Detection precision | 1.00 |
| Detection recall | 1.00 |
| Model calls | 8 of 12 exceptions |

### Exception routing

| Route | Count | Value |
|---|---|---|
| Auto-resolved | 11 | Rs 1,13,681.78 |
| Escalated for review | 0 | Rs 0.00 |
| Unresolvable | 1 | Rs 10,882.80 |

### How to read these numbers

**Detection is exact.** Every planted exception was found and nothing
else was flagged. This tests the reconciler, not the model.

**Four of twelve resolved without a model call.** A single candidate
matching the gap exactly, and a gap no refund can cover even summed, are
arithmetic rather than judgment. The classifier is reserved for evidence
that is genuinely ambiguous.

**Nothing escalated, and that is a finding rather than a success.** Two
settlements in this dataset contain both a chargeback and an old-cycle
refund. The verdict schema was extended to hold a list of causes with an
attributed amount each, and routing escalates any verdict covering less
than 90% of the gap — a mechanism verified by test at 58% coverage and
0.99 confidence.

The model does not produce partial attributions. Across 8
classifications it returned exactly one cause every time and attributed
the full gap to it, including on the settlement ground truth records as
two chargebacks plus a refund. Coverage is therefore always 100% and the
gate never fires. Permitting an answer is not the same as eliciting it.
Recorded as F-12.

## Architecture

    generate.py     synthetic data + ground truth
          |
          v
    data/*.csv      payments, refunds, settlements
          |
          v
    loader.py       validate on read, collect bad rows
          |
          v
    reconciler.py   rebuild each settlement, compute the gap
          |
          +---> matched
          |
          v
    evidence.py     gather candidates, compute amount matches
          |
          v
    pipeline.py     deterministic resolution attempted first
          |
          v
    classifier.py   LLM: attribute the gap     <-- only LLM step
          |
          v
    pipeline.py     coverage and confidence gate, audit record
          |
          v
    evaluate.py     score against ground truth

Every stage except `classifier.py` is deterministic. Full design notes,
trade-offs and limitations are in
[docs/architecture.md](docs/architecture.md).

### What is deliberately not used

**LangGraph or an agent runtime.** The control flow is static — every
settlement takes the same path, and the only branches are numeric
thresholds. A graph runtime would add a dependency and a layer of
indirection without enabling anything.

**A vector database.** There is no retrieval problem here. Candidate
refunds are selected by date range and payment lineage, which is a
lookup, not a similarity search.

**A web UI.** The deliverable is a measured reconciliation run, not a
dashboard.

## Where the AI is, and where it isn't

**Python does all arithmetic and all matching.** Grouping payments into
settlement batches, computing fees and GST, summing, comparing against
the bank credit, searching candidate refunds for exact and pairwise
amount matches, and computing how much of a gap survives them. All of it
is exact, free, and identical on every run.

**The model does one thing: attribute a gap it is handed.** It receives
the computed gap, the candidate refunds, and the amount-match findings
as facts. It never adds anything up.

    The model classifies. It never calculates.

**Unambiguous cases never reach the model.** A single candidate matching
the gap exactly resolves in code at confidence 1.0. So does a gap no
refund can cover even summed — that is a chargeback by definition.
Calling a model to confirm what arithmetic has already proven is waste.

**The model's judgment is required where matching fails.** A settlement
whose gap is partly explained by a refund, with a remainder that has no
record anywhere, cannot be attributed by any rule. Deciding what that
remainder is — a chargeback, a partially matched refund, or something
unmodelled — is judgment over incomplete evidence.

**Low confidence or partial coverage escalates rather than guessing.** A
verdict holds a list of causes, each with the amount of the gap it
accounts for. Routing escalates anything covering less than 90% of the
gap or falling below 0.85 confidence; a verdict with no attributable
cause goes to the unresolvable list. In a finance system a silent wrong
answer costs far more than an unnecessary review.

See the results section for what happened when this was measured — the
mechanism works and the model does not currently use it.

## Development record

Twelve runtime failures were logged while building this, including the
wrong theories pursued along the way:
[FAILURES.md](FAILURES.md).

The most instructive: the classifier would not emit a `chargeback` label
across four prompt revisions. The model stated the reason in its own
first response — that the schema permitted only three causes — and it was
read as hedging. `models.py` contained three `class Cause` definitions
accumulated by pasting rather than editing, and `ExceptionVerdict` had
captured an earlier three-value one. Roughly four hours on a prompt
problem that was a file hygiene problem.