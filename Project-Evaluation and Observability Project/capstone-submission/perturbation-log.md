# Perturbation Log

Two experiments per system: the **starter** perturbation from the Instructions (baseline — confirms
the documented behavior), and an **original** one (designed here). Predictions were written before
each run; where a prediction was wrong, the log says so rather than being retrofitted.

Supporting artifacts are in `perturbations/system{1,2,3}/`.

---

## System 1 — validated, routed pipeline

### 1A (starter) — blank a required field so the information is genuinely absent

- **Change I made (file + what I changed):** copied `data/policies/POL-2025-001.txt` to
  `perturbations/system1/POL-2025-001-premium-blanked.txt` and replaced the premium value line
  `   Total Policy Premium ........................  $ 1,847.62`
  with `*** (premium schedule not enclosed with these declarations) ***`. The bundled corpus was not
  modified. `premium_amount` is one of the five `_REQUIRED_FIELDS` in `policy_extractor/validator.py`.
- **Command I ran:**
  ```
  .venv/bin/policy-extractor extract perturbations/system1/POL-2025-001-premium-blanked.txt \
      --policy-id POL-2025-001-PERTURBED --max-retries 3
  ```
- **What I predicted:** the extractor returns `premium_amount: null`; the validator categorizes this
  as `missing_source` rather than `format`; retry is skipped and the record escalates after exactly
  **one** API call, despite `--max-retries 3`.
- **What actually happened (key output line):** exit code `1`, and:
  ```json
  { "kind": "escalation",
    "category": "missing_source",
    "detected_pattern": "premium_amount_absent",
    "field": "premium_amount",
    "reason": "Field 'premium_amount' returned null — the source document does not contain this
               information. Retry is futile; escalate to human review." }
  ```
  The stderr log contains exactly one `HTTP Request: POST .../v1/messages` line
  (`A-perturbed-premium-blanked.stderr`). Prediction held in full.
- **How this differs from the unperturbed run:** the same document unmodified
  (`A-baseline-unperturbed.json`) extracts `premium_amount: 1847.62` at confidence `1.0`, exits `0`,
  and also makes one API call. So the API-call count is identical — **what changed is the terminal
  state, not the effort spent**. That is the whole point of the futile/recoverable split: the system
  spent no budget discovering that the document is silent, because `missing_source` is decided from
  the *response*, not from a retry attempt. A `format` or `consistency` failure, by contrast, does
  retry — visible in `01-policy-pipeline/pipeline-run.txt`, where POL-2025-010 logs two
  `validation_failed` lines before succeeding.

### 1B (original) — signal isolation: which of the three routing signals actually decides?

- **Change I made:** two probes.
  1. **Document perturbation.** Added one line to a copy of POL-2025-001
     (`POL-2025-001-endorsement-exceeds-coverage.txt`):
     `   - Excess Liability Endorsement (AU-90)  $750,000 limit`
     while the policy's own coverage limit remains $100,000 — designed to trip the *integration*
     signal specifically, since `_check_coverage_limit_vs_endorsements` fails when
     `coverage_limit < sum(endorsement.limit)`.
  2. **Deterministic truth table.** Drove `route_extraction` directly with all 8 combinations of the
     three signals, constructing the inputs rather than eliciting them from the model
     (`C-routing-truth-table.txt`). No API calls, so no model variance.
- **Command I ran:**
  ```
  .venv/bin/python signal_probe.py <doc> <policy-id>      # B-*-signals.txt
  .venv/bin/python truth_table.py                         # C-routing-truth-table.txt
  python3 signal_dominance.py                             # D-signal-dominance.txt
  ```
- **What I predicted:** the perturbed document trips integration *alone*, cleanly separating it from
  the confidence and reviewer signals.
- **What actually happened:** the integration check failed exactly as designed —
  ```
  [FAIL] coverage_limit_exceeds_endorsement_sum: coverage_limit=100000 is less than the sum of
         endorsement limits (750000). The primary coverage cannot be smaller than what the
         endorsements promise.
  ```
  **But the isolation failed**: the reviewer *also* disagreed on three fields in the same run, so the
  observed signal set was `['reviewer', 'integration']`, not `['integration']`. Chasing that led to
  the more interesting result. Counting signal firings across the nine records of my own live routing
  output (`D-signal-dominance.txt`):

  | signal | fired on | rate |
  |---|---|---|
  | reviewer | 8 / 9 | 89% |
  | confidence | 1 / 9 | 11% |
  | integration | 0 / 9 | 0% |

  Removing the reviewer signal drops `human_review` from **8 to 1**. Removing confidence or
  integration changes nothing. On **7 of 9** records the reviewer was the *only* signal that fired.
  The truth table confirms the combination rule is **OR, not AND**: any single signal diverts to
  `human_review`, and `auto_approve` requires all three clear simultaneously.
- **How this differs from the unperturbed run:** the unperturbed pipeline shows the same aggregate
  counts but gives no way to attribute them. The perturbation plus the counterfactual shows that on
  this corpus the router is effectively a *reviewer-only* router wearing three-signal clothing — and
  that the integration check, which never fired once on real data, is only demonstrably alive because
  I perturbed a document specifically to trip it. A check that never fires in production is
  indistinguishable from a check that is broken; this experiment is the difference.

---

## System 2 — schema-enforced two-pass extraction

### 2A (starter) — contrast a flagged document with a clean one

- **Change I made:** none to the inputs; this is the documented contrast between two shipped
  fixtures, `income_sum_mismatch.txt` (whose stated total disagrees with its own line items) and
  `appraisal_informal_sqft.txt` (internally consistent).
- **Command I ran:**
  ```
  .venv/bin/mortgage-extract fixtures/documents/income_sum_mismatch.txt   --mode replay -v ; echo $?
  .venv/bin/mortgage-extract fixtures/documents/appraisal_informal_sqft.txt --mode replay -v ; echo $?
  ```
- **What I predicted:** the first reports a discrepancy and exits non-zero; the second is clean and
  exits `0`.
- **What actually happened:** exactly that.
  ```json
  "discrepancies": [ { "field": "total_monthly_income",
                       "calculated": 9642.17, "stated": 10892.17, "delta": -1250.0 } ]
  ```
  exit `1`. The delta is exactly the $1,250.00 bonus — the document's own `TOTAL MONTHLY EARNINGS`
  line double-counts it. The appraisal run exits `0` with `"consistent": true`.
- **How this differs from the unperturbed run:** the appraisal *is* the unperturbed comparison. The
  informative detail is that the appraisal passes with `"income"` entirely null — it is not "clean
  because the arithmetic checked out," it is clean because `calculated_monthly_total` returns `None`
  and the validator's `if calculated is not None and stated is not None` guard skips the check
  altogether. Verified directly in `null-vs-zero-probe.txt`.

### 2B (original) — binary-search the consistency tolerance boundary

- **Change I made:** starting from the real replayed extraction of `income_sum_mismatch.txt`, varied
  **only** `stated_monthly_total` so that `delta = calculated − stated` takes the values
  0.00, 0.50, 0.99, 0.999, 1.00, 1.001, 1.01, 1.50, 1250.00. Every component field was left exactly
  as extracted. `config.DEFAULT_TOLERANCE_USD` is `1.00`.
- **Command I ran:** `.venv/bin/python tolerance_probe.py` → `tolerance-boundary-probe.txt`
- **What I predicted:** `validator.py` compares `if abs(delta) > tolerance`, a strict `>`, so a delta
  of exactly $1.00 passes and anything above it is flagged.
- **What actually happened:** the first half held, the second half **did not**.
  ```
   target delta       stated   |delta|  consistent?
          1.000     9641.170     1.000         True     <- as predicted
          1.001     9641.169     1.001         True     <- NOT predicted
          1.010     9641.160     1.010        False
  ```
  A delta of $1.001 is *not* flagged. The cause is two lines acting in sequence:
  ```python
  delta = round(calculated - stated, 2)   # rounds FIRST
  if abs(delta) > tolerance:              # compares SECOND
  ```
  `1.001` rounds to `1.00`, and `1.00 > 1.00` is `False`. The **effective** threshold is therefore
  $1.005, not the documented $1.00 — the rounding silently widens the tolerance by half a cent.
- **How this differs from the unperturbed run:** the unperturbed run shows a delta of $1,250.00,
  three orders of magnitude past the threshold, which tells you nothing about where the threshold
  actually is. Only the sweep distinguishes the *documented* contract (`DEFAULT_TOLERANCE_USD = 1.00`)
  from the *enforced* one ($1.005). The gap is harmless at this magnitude, but it is exactly the kind
  of drift between a named constant and its runtime behavior that a reader of either line alone
  cannot see.

---

## System 3 — multi-source synthesis

### 3A (starter) — run with and without `--simulate-timeout`

- **Change I made:** no input edit; the `--simulate-timeout` flag forces the logistics reader to fail.
- **Command I ran:**
  ```
  .venv/bin/supply-chain-investigate meridian --offline
  .venv/bin/supply-chain-investigate meridian --offline --simulate-timeout
  diff briefing.md briefing-timeout.md
  ```
- **What I predicted:** the run completes; logistics-derived metrics move to Incomplete annotated as
  a timeout; the remaining sections are unchanged.
- **What actually happened:** the run completed (exit `0`) and the header gained
  `> Sources unavailable: logistics unavailable (timeout)`. `late_shipment_count` moved to Incomplete
  carrying its cause (`_[missing source: timeout reading logistics]_`), distinct from the other
  Incomplete entry (`_[missing source: no source reported this metric]_`). But one prediction was
  **wrong**: the remaining sections were *not* unchanged.
  ```
  normal run:   ## Contested        ### on_time_delivery_rate _[2 sources, conflicting]_ ⚠️ ESCALATE
                                        95.0% — supplier_audit (2026-04-10)
                                        78.0% — logistics     (2026-04-05)
  timeout run:  ## Well-Established ### on_time_delivery_rate _[single source only]_
                                        95.0% — supplier_audit (2026-04-10)
                ## Contested        _none_
  ```
  The contested metric was **promoted to Well-Established**, and the surviving value is the
  supplier's own self-reported 95% — the optimistic one. The pessimistic 78% came from our own
  logistics data. The Contested section reads `_none_`.
- **How this differs from the unperturbed run:** graceful degradation is not neutral. Losing a source
  did not merely reduce coverage; it converted a **known disagreement into false confidence**, in the
  reassuring direction. The `_[single source only]_` badge and the header banner are the only things
  separating this briefing from a reader who concludes on-time delivery is fine. Full analysis in
  `03-supply-chain/timeout-diff.txt`.

### 3B (original) — locate the conflict-detection threshold

- **Change I made:** copied `data/` to a scratch tree and rewrote
  `data/meridian/audit.json → metrics[on_time_delivery_rate].value` to each of
  78, 82, 85, 86, 86.6, 86.7, 87, 90, 95, re-running the full investigation each time. The logistics
  reader was untouched and always derives 78% from the 50-row CSV (39 on-time). All runs `--offline`,
  so the news reader could not add variance. The bundled corpus was not modified.
- **Command I ran:**
  ```
  .venv/bin/supply-chain-investigate meridian --offline --data-root /tmp/sc-perturb/data
  ```
  once per value → `conflict-threshold-sweep.txt`
- **What I predicted:** `synthesis.py` sets `REL_TOL = 0.10` and `_disagree()` computes
  `(hi − lo) / max(|lo|, |hi|) > REL_TOL`. With `lo` pinned at 78 and `hi` the audit value X,
  the metric should be Contested when `(X − 78)/X > 0.10`, i.e. `X > 86.67`.
- **What actually happened:** confirmed to the resolution tested. The flip lands between
  86.6 (rel.diff `0.0993` → Well-Established, "corroborated across 2 sources") and
  86.7 (rel.diff `0.1003` → Contested, "2 sources, conflicting", ⚠️ ESCALATE), bracketing 86.67.
- **How this differs from the unperturbed run:** the unperturbed briefing shows only that 95 vs 78 is
  contested — you cannot tell whether the test is exact, absolute, or relative, nor how close two
  sources may be before the disagreement stops being reported. The sweep shows the tolerance is
  **relative to the larger value**, and therefore asymmetric: an audit reporting 86.6% against our
  measured 78% is filed as "corroborated across 2 sources," the same badge given to genuine
  agreement, with the 8.6-point spread neither shown nor escalated. One relative tolerance is doing
  double duty — absorbing measurement noise *and* defining business-relevant disagreement — and 10%
  is a reasonable answer to the first question but a poor one to the second for a service-level
  metric.

---

## Cross-cutting note

Three of these six experiments probed a **threshold** rather than a happy path: the retry boundary
(1A), the $1.00 consistency tolerance (2B), and the 10% conflict tolerance (3B). In all three the
unperturbed run sits far from the boundary and therefore reveals nothing about where it is. Two of
the three turned up a gap between the documented constant and the enforced behavior — $1.00 vs an
effective $1.005, and "10% tolerance" vs an asymmetric band that calls 78-vs-86.6 agreement.
Thresholds are the part of a validation system least exercised by normal traffic and least visible
in normal output, which is precisely why they are worth perturbing deliberately.
