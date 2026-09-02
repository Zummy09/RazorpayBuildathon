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