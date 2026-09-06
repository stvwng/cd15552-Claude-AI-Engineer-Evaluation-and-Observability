# Evidence Index

Every rubric requirement mapped to the artifact that satisfies it. The rubric's one hard rule is that
a reviewer must be able to open any cited artifact and find the exact quoted value; this table is the
lookup.

Paths are relative to `capstone-submission/`.

---

## Reproduce & Verify

### Reproduce and verify reference systems from source

| Requirement | Artifact | What to look for |
|---|---|---|
| Full test-suite output, all three systems, passing count visible | `01-policy-pipeline/tests.txt` | `45 passed, 3 skipped` (RUN A, offline) and `48 passed` (RUN C, live) |
| | `02-mortgage-extraction/tests.txt` | `25 passed` — plus a `--collect-only` note explaining that the solution README's "28 acceptance tests" does not match the shipped suite |
| | `03-supply-chain/tests.txt` | `34 passed` |
| Static-analysis output (mypy + ruff), all three, no errors | `01-policy-pipeline/static-checks.txt` | `Success: no issues found in 11 source files` / `All checks passed!`, both `exit=0` |
| | `02-mortgage-extraction/static-checks.txt` | `Success: no issues found in 11 source files` / `All checks passed!`, both `exit=0` |
| | `03-supply-chain/static-checks.txt` | `Success: no issues found in 8 source files` / `All checks passed!`, both `exit=0`. Includes a documented diagnosis of why `--python-version 3.12` is required on this machine (a numpy stub, not project code) |
| Environment note: Python version and OS | `environment.txt` | macOS 26.5.2 (25F84), Python 3.12.3, git rev `d5951cc`, plus `pip freeze` per venv |

**Beyond the requirement:** each suite was run twice offline with byte-identical summary lines
(RUN A / RUN B in each `tests.txt`) as direct evidence that the offline fixtures make the suites
deterministic.

---

## Demonstrate Behavior

### System 1 — validation-driven retry, batch processing, deterministic HITL routing

| Requirement | Artifact | What to look for |
|---|---|---|
| Full end-to-end pipeline run over the bundled document set | `01-policy-pipeline/pipeline-run.txt` | Live run over all 10 `data/policies/POL-*.txt`; summary shows `auto_approve: 0`, `human_review: 8`, `spot_check: 1`, `escalations: 1` |
| The generated routing-decision output file | `01-policy-pipeline/routing_decisions.json` | 9 records, each with `decision`, `reason`, and the three signal arrays |
| Sliced (policy_type × field) calibration report | `01-policy-pipeline/calibration-report.txt` | `umbrella exclusions n=2 conf=0.93 acc=0.00 brier=0.865`; `OVERALL brier=0.291` |
| | `01-policy-pipeline/routing-tests.txt` | The routing test that exercises calibration: `9 passed` |
| Reflection names a `human_review` record and the signal that drove it | `reflection-brief.md` §1b | POL-2025-002 — reviewer signal alone, all confidences ≥ 0.95 |

**Beyond the requirement:**

| Artifact | Finding |
|---|---|
| `01-policy-pipeline/seed-determinism.txt` | Two identical live runs with identical `--seed 42` produced *different* decisions for POL-2025-007. Separates the three sources of run-to-run behavior: pure router, seeded sampler, nondeterministic model |
| `01-policy-pipeline/sampler-seed-probe.txt` | Controlled probe of `apply_stratified_spot_check` with the model held out: seed 42 twice → identical picks; seed 7 → different picks; no stratum ever dropped, where naive `floor(10%)` samples zero from `umbrella` (n=3) and `other` (n=1) |
| `01-policy-pipeline/stratum-coverage.txt` | Per-stratum spot-check coverage computed from the learner's own routing output |
| `01-policy-pipeline/run1-seed42.json`, `run2-seed42.json` | The two live runs being compared |

### System 2 — schema-enforced two-pass extraction with arithmetic-consistency validation

| Requirement | Artifact | What to look for |
|---|---|---|
| Run over at least one document showing classified type + structured result | `02-mortgage-extraction/extract-run.txt` | `type=appraisal`, `tool=extract_appraisal`, full extraction, `exit=0`. Source document included for comparison |
| | `02-mortgage-extraction/missing-field-run.txt` | `type=income_verification`; `"bonus_monthly": null` |
| Run where the consistency validator reports a discrepancy | `02-mortgage-extraction/discrepancy-run.txt` | `"calculated": 9642.17, "stated": 10892.17, "delta": -1250.0`, `exit=1` |
| Reflection explains why a missing field returned null, not a fabrication | `reflection-brief.md` §2b | Points to the `float \| None` union in `models.py`; contrasts with System 3's non-nullable `source_date` |

**Beyond the requirement:**

| Artifact | Finding |
|---|---|
| `02-mortgage-extraction/live-vs-replay.txt` | Three identical live calls, three different outcomes: fabricated-and-accepted, correct, and schema-rejected. Forced `tool_choice` did not guarantee conformance (1 in 3 rejected), and conformance did not guarantee truth (1 in 3 fabricated) |
| `perturbations/system2/null-vs-zero-probe.txt` | Empirical confirmation of the `None`-vs-`0.0` design claim in the solution README, including the same-unit invariant on `calculated_monthly_total` |

### System 3 — provenance-preserving multi-source synthesis under conflict and source failure

| Requirement | Artifact | What to look for |
|---|---|---|
| Full investigation run and briefing with all three sections | `03-supply-chain/investigation-run.txt`, `03-supply-chain/briefing.md` | `## Well-Established`, `## Contested`, `## Incomplete`; logistics data present |
| Run with source-failure simulation, completing with the failed source annotated | `03-supply-chain/timeout-run.txt`, `03-supply-chain/briefing-timeout.md` | `exit=0`; `> Sources unavailable: logistics unavailable (timeout)`; `### late_shipment_count _[missing source: timeout reading logistics]_` |
| Reflection quotes a conflicting-metric pair and explains why both are retained | `reflection-brief.md` §3a | `95.0 percent — supplier_audit (2026-04-10)` vs `78.0 percent — logistics (2026-04-05)` |

**Beyond the requirement:**

| Artifact | Finding |
|---|---|
| `03-supply-chain/timeout-diff.txt` | Mechanical diff of the two briefings. Surfaces that `on_time_delivery_rate` is **promoted from Contested to Well-Established** when logistics dies — a known disagreement becomes false confidence, and the surviving value is the supplier's optimistic self-report |
| `03-supply-chain/live-vs-offline-briefing.txt` | Live vs recorded news extraction (9 vs 18 metrics). Documents that the Contested section is byte-identical because it comes from deterministic readers, and that the required non-nullable `source_date` causes the model to **fabricate dates** for an undated article (`2024-01-01` live, `2026-03-09` recorded) |
| `03-supply-chain/briefing-live.md` | The live briefing |

---

## Stress-Test & Reflect

### Trigger and document targeted edge-case behavior through controlled input perturbation

| Requirement | Artifact | What to look for |
|---|---|---|
| A perturbation log with, for each of the three systems, one deliberate change + command + result | `perturbation-log.md` | Six entries — the starter perturbation **and** an original one per system |
| Each entry contrasts observed behavior with the unperturbed run | `perturbation-log.md` | Every entry ends with a "How this differs from the unperturbed run" paragraph |

Supporting artifacts:

| System | Experiment | Artifacts |
|---|---|---|
| 1 | **1A starter** — blank a required field | `perturbations/system1/POL-2025-001-premium-blanked.txt`, `A-perturbed-premium-blanked.json` (escalation, `missing_source`), `A-perturbed-premium-blanked.stderr` (exactly one API call), `A-baseline-unperturbed.json` |
| 1 | **1B original** — signal isolation | `POL-2025-001-endorsement-exceeds-coverage.txt`, `B-baseline-signals.txt`, `B-perturbed-integration-signals.txt`, `C-routing-truth-table.txt` (all 8 combinations), `D-signal-dominance.txt` (reviewer 8/9, confidence 1/9, integration 0/9) |
| 2 | **2A starter** — flagged vs clean | `02-mortgage-extraction/discrepancy-run.txt` vs `extract-run.txt` |
| 2 | **2B original** — tolerance boundary | `perturbations/system2/tolerance-boundary-probe.txt` — documented $1.00 tolerance is enforced as $1.005 because `delta` is rounded to 2dp before comparison |
| 3 | **3A starter** — `--simulate-timeout` | `03-supply-chain/timeout-diff.txt` |
| 3 | **3B original** — conflict threshold sweep | `perturbations/system3/conflict-threshold-sweep.txt` — nine perturbed values of `audit.json`; boundary located between 86.6 and 86.7, confirming the predicted 86.67 |

All perturbation scripts are included (`signal_probe.py`, `truth_table.py`, `signal_dominance.py`,
`tolerance_probe.py`, `null_probe.py`, `live_vs_replay.py`) so each experiment can be re-run.

### Analyze evaluation, reliability, and observability tradeoffs grounded in observed evidence

| Requirement | Artifact | What to look for |
|---|---|---|
| Every prompt answered, each answer referencing a specific artifact | `reflection-brief.md` §§0–4 | All 12 prompts (0, 1a–1c, 2a–2c, 3a–3c, 4a–4c) answered; every answer quotes a value and names its file |
| Synthesis section connecting the three systems to a reliability principle | `reflection-brief.md` §4a–4c | §4c gives a concrete workflow (vendor-security review intake), a pattern choice with reasoning drawn from observed evidence, and an eight-row instrumentation table where each row names the run that motivated it |

---

## Screenshots

One per system, each showing the same run as its sibling text capture.

| Screenshot | Command | Shows |
|---|---|---|
| `01-policy-pipeline/screenshots/calibration-report-sliced.png` | `python calibration_report.py` | `umbrella/exclusions conf=0.93 acc=0.00 brier=0.865` vs `OVERALL brier=0.291` |
| `02-mortgage-extraction/screenshots/consistency-discrepancy-exit1.png` | `mortgage-extract income_sum_mismatch.txt --mode replay -v` | two-pass log, `delta: -1250.0`, exit `1` |
| `03-supply-chain/screenshots/graceful-degradation-timeout.png` | `supply-chain-investigate meridian --offline --simulate-timeout` | outage banner, `## Contested _none_`, two distinct "missing source" causes |

The text captures alongside them carry the full untruncated output and are the ones to search for
exact values.

---

## Corpus integrity

No bundled corpus or fixture was modified. All perturbations were made on copies, and the live
`--mode record` run for System 2 was pointed at a throwaway cache directory rather than
`fixtures/recorded_responses/`. Verified with `git status --porcelain` at the end of
`02-mortgage-extraction/live-vs-replay.txt`, and reproducible via `run_all.sh`.

---

## Self-audit

Every row above resolves to a file that exists in this pack. Two documentation discrepancies found in
the course material are recorded rather than smoothed over:

1. System 2's solution README claims 28 acceptance tests; the shipped suite collects and passes 25
   (`02-mortgage-extraction/tests.txt`).
2. System 3's `mypy` invocation fails out of the box because `pyproject.toml` pins
   `python_version = "3.11"` while numpy's stubs require 3.12+ syntax; the error is in a third-party
   stub, not project code (`03-supply-chain/static-checks.txt`).
