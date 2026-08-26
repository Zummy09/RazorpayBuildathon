# Failure Journal

Every runtime failure found while building this system, what caused it,
and how the system was changed to survive it.

| # | Symptom | Root cause | What I tried | Fix | Cost |
|---|---------|------------|--------------|-----|------|
| 1 | Settlement totals exceeded actual captured payments by ₹7,39,529 across 30 settlements | `build_settlements` grouped payments by date but did not filter on status, so all 101 failed payments were included in gross — and fees were deducted on them too, which never happens in reality | Checked fee maths first, assumed the rounding was wrong. Compared settlement total against captured-only gross, saw the gap was ~101 × avg payment | Filter batch to `status == CAPTURED` before summing | ~40 min. Would have silently broken every downstream match rate |