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
    cd settlement-reconciliation-agent
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

## Results

Measured on a 30-day synthetic dataset: 1,380 payments, 67 refunds,
6 chargebacks, 30 settlements. Ground truth is written by the generator
at the moment each problem is planted, and is read only by the evaluator.

| Metric | Value |
|---|---|
| Settlements processed | 30 |
| Reconciled cleanly | TBD |
| Exceptions raised | TBD |
| Detection precision | TBD |
| Detection recall | TBD |
| Cause classified correctly | TBD |
| Evidence cited correctly | TBD |
| Model calls | TBD of TBD exceptions |

### Exception routing

| Route | Count | Value |
|---|---|---|
| Auto-resolved | TBD | TBD |
| Escalated for review | TBD | TBD |
| Unresolvable | TBD | TBD |

The unresolvable list is not a failure to hide. A settlement whose gap
is partly explained by a refund and partly by a deduction with no
record in the merchant's data cannot be attributed with confidence, and
the system says so rather than guessing.

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
    classifier.py   LLM: name the cause          <-- only LLM step
          |
          v
    pipeline.py     confidence gate, audit record
          |
          v
    evaluate.py     score against ground truth

Every stage except `classifier.py` is deterministic.

### What is deliberately not used

**LangGraph or an agent runtime.** The control flow is static — every
settlement takes the same path, and the only branch is a numeric
threshold. A graph runtime would add a dependency and a layer of
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
amount matches. All of it is exact, free, and identical on every run.

**The model does one thing: name the cause of a gap it is handed.** It
receives the computed gap, the candidate refunds, and the amount-match
findings as facts. It never adds anything up.

    The model classifies. It never calculates.

**Unambiguous cases never reach the model.** A single candidate refund
matching the gap exactly is resolved in code at confidence 1.0. Calling
a model to confirm what arithmetic has already proven is waste.

**The model's judgment is required where matching fails.** A settlement
whose gap no refund explains, alone or in combination, has money in it
with no record in the merchant's data. Deciding whether that is a
chargeback, a partially-matched old-cycle refund, or something
unmodelled is a judgment over incomplete evidence — which is what a
language model is for and what a rule cannot do.

**Low confidence escalates rather than guesses.** Verdicts below the
0.85 threshold route to human review; a verdict of `unknown` routes to
the unresolvable list. In a finance system a silent wrong answer costs
far more than an unnecessary review.

### Tests

    pytest

Nine tests covering the deterministic core: fee and GST arithmetic,
T+2 batch selection, exclusion of failed payments, and the refund
justification rule. No API calls required — the components that handle
money are verifiable without a model being available.