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