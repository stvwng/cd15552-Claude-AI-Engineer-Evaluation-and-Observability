# Capstone Plan — Evaluation & Observability

**Goal:** produce a `capstone-submission/` evidence pack that meets every rubric line, plus a set of
deliberate "stand-out" moves the instructions explicitly reward, and finish with a teaching primer.

**Key facts established during discovery**

| Fact | Value |
|---|---|
| Python | 3.12.3 |
| OS | macOS 26.5.2 (Darwin 25.5.0), build 25F84 |
| `ANTHROPIC_API_KEY` | **set** → live runs are possible (the instructions' "no API access" fallback is not needed) |
| venvs today | exist only in `*/starter/`; **none of the three `solution/` dirs has one yet** |
| Heaviest install | supply-chain solution (`chromadb` + `sentence-transformers` → torch, ~90 MB model on first run) |
| System 1 live cost | ~10 docs × (extract + review) ≈ 20–30 API calls |
| Mortgage default model | `claude-haiku-4-5-20251001` (`config.DEFAULT_MODEL`) |

**Submission root:** `Project-Evaluation and Observability Project/capstone-submission/`

---

## Phase 0 — Environment (rubric: *Reproduce & Verify → environment note*)

1. Create `capstone-submission/` with the exact tree from `README.md`, plus two additions
   (`evidence-index.md`, `run_all.sh`) described in Phase 5.
2. Build a venv **inside each of the three `solution/` dirs** and `pip install -e ".[dev]"`:
   - `Build a Validated, Routed Insurance Policy Extraction Pipeline/04-hitl-routing/solution/`
   - `Build a Resilient Mortgage Document Extraction System/04-validate-mathematical-consistency/solution/`
   - `Investigate Supply Chain Risk with Multi-Source Synthesis/03-resilient-coordinator/solution/`
   Do the supply-chain one first and in the background — it pulls torch.
3. Warm the embedding model once (`all-MiniLM-L6-v2`) so timing captures aren't dominated by a download.
4. Write `environment.txt`: `python3 --version`, `sw_vers`, `uname -a`, the venv creation commands, and
   **`git rev-parse HEAD`** so a reviewer can pin the exact source revision.
   - **Stand-out:** append `pip freeze` per venv (as `environment.txt` appendices) — exact dependency
     pins make the run genuinely reproducible, not just described.

**Gate:** all three `pip install -e ".[dev]"` succeed.

---

## Phase 1 — Reproduce & Verify (rubric: test output + static analysis, all three systems)

For each system, from its `solution/` dir, capture with `| tee`:

| Artifact | Command |
|---|---|
| `01-policy-pipeline/tests.txt` | `.venv/bin/pytest tests/ -v` (expect **45 passed, 3 skipped**) |
| `01-policy-pipeline/static-checks.txt` | `.venv/bin/mypy policy_extractor/` then `.venv/bin/ruff check policy_extractor/ tests/` |
| `02-mortgage-extraction/tests.txt` | `.venv/bin/pytest tests/ -v` (expect **28** acceptance tests) |
| `02-mortgage-extraction/static-checks.txt` | `.venv/bin/mypy mortgage_extractor/` + `ruff check mortgage_extractor/ tests/` |
| `03-supply-chain/tests.txt` | `.venv/bin/pytest tests/ -v` (use `-v` not `-q` — the rubric wants the **count visible**) |
| `03-supply-chain/static-checks.txt` | `.venv/bin/mypy supply_chain_risk/` + `ruff check supply_chain_risk/ tests/` |

Note: the instructions say `pytest tests/ -q` for System 3. Use `-v` instead — the rubric requires a
visible passing count. `-q` still prints a summary line, but `-v` removes all doubt.

**Stand-out moves**
- **Determinism proof.** Run each suite twice and capture both; a second identical summary line is
  direct evidence the offline fixtures make the suite deterministic. Save as `tests-rerun.txt`.
- **Timing.** Prefix each capture with `date -u` and wrap in `time` — a reviewer sees wall-clock cost,
  which is the honest counterweight to "just add more validation layers."
- **Zero-error proof for static analysis.** Capture the exit code (`; echo "exit=$?"`) after each mypy
  and ruff invocation. "Success: no issues found" plus `exit=0` is unambiguous.

**Gate:** three green suites, six clean static-analysis runs.

---

## Phase 2 — Demonstrate Behavior

### 2.1 System 1 — validated, routed pipeline (live)

```
.venv/bin/policy-extractor pipeline data/policies/ \
  --routing-out routing_decisions.json --spot-check-pct 0.1 --seed 42 | tee pipeline-run.txt
```

- Copy `routing_decisions.json` into `01-policy-pipeline/`.
- The printed summary must show `auto_approve` / `human_review` / `spot_check` counts and
  `escalations` + `pattern_summary`.
- Calibration report: `.venv/bin/python calibration_report.py | tee calibration-report.txt`
  (copy the provided `calibration_report.py` into the solution dir first). Expect the
  `umbrella / exclusions` cell at `acc=0.00` while `conf=0.93`, with a moderate `OVERALL brier`.

**Stand-out moves**
- **Run it live.** The instructions offer `pytest tests/test_us04_routing.py -v` as a no-API
  substitute. Doing the real run over all ten bundled policies is strictly more evidence — capture
  the substitute test run *as well*, so the pack shows both paths.
- **Seed-sensitivity experiment.** Run the pipeline three times: `--seed 42`, `--seed 7`, and
  `--seed 42` again. `diff` the three `routing_decisions.json` files. The expected result — routing
  decisions identical across seeds, only the `spot_check` selections moving, and seed 42 reproducing
  byte-for-byte — is a *direct empirical demonstration* that the router is deterministic and only the
  sampler is stochastic. This is the single most persuasive artifact in the pack. Save as
  `seed-determinism.txt` + the three JSONs.
- **Stratum-preservation check.** Write a tiny read-only script that groups
  `routing_decisions.json` by `policy_type` and prints, per stratum, `n` and how many were
  spot-checked. It shows empirically that a small stratum is never dropped to zero — the claim
  `apply_stratified_spot_check` makes, verified against the learner's own output rather than asserted.
  Save as `stratum-coverage.txt`.
- Capture `--verbose`/stderr logs too: `review_disagreement policy_id=… fields=[…]` lines are the
  observability signal the reflection's 1b answer will quote.

### 2.2 System 2 — schema-enforced two-pass extraction

```
.venv/bin/mortgage-extract fixtures/documents/appraisal_informal_sqft.txt --mode replay -v | tee extract-run.txt ; echo "exit=$?"
.venv/bin/mortgage-extract fixtures/documents/income_missing_bonus.txt   --mode replay -v | tee missing-field-run.txt ; echo "exit=$?"
.venv/bin/mortgage-extract fixtures/documents/income_sum_mismatch.txt    --mode replay -v | tee discrepancy-run.txt ; echo "exit=$?"
```

Each run must show the classified document type and the structured extraction. Exit codes matter:
`0` for consistent, `1` for a reported discrepancy — capture them.

**Stand-out moves**
- **Run one fixture live with `--mode record`** and diff the result against the `--mode replay`
  output. Identical structured output from a fresh API call proves the recorded fixtures are faithful
  and the offline evidence isn't an artifact of stale caching. Save as `live-vs-replay.txt`.
- **`--verbose` on every run** so the two-pass structure (classify call, then forced-`tool_choice`
  extract call) is visible in the log, not just asserted in prose.
- The `-v` logs plus the three exit codes let the reflection cite an actual line rather than paraphrase.

### 2.3 System 3 — multi-source synthesis

```
.venv/bin/supply-chain-investigate meridian --offline | tee investigation-run.txt
.venv/bin/supply-chain-investigate meridian --offline > briefing.md
.venv/bin/supply-chain-investigate meridian --offline --simulate-timeout | tee timeout-run.txt
```

Briefing must show Well-Established / Contested / Incomplete and the logistics data; the on-time
delivery conflict (~95% vs ~78%) must appear with **both** values attributed and dated.

**Stand-out moves**
- **`diff` the two briefings** (normal vs `--simulate-timeout`) into `timeout-diff.txt`. The rubric
  asks the learner to *contrast* behaviors; a diff makes the contrast mechanical and unarguable —
  exactly which claims vanish, and exactly what annotation replaces them.
- **Run the live path once** (no `--offline`, using `AnthropicNewsExtractor`) and diff against the
  recorded run. This shows the recorded fixtures are representative and demonstrates the system
  against a real model, which the offline-only path can't. Save as `live-vs-offline-briefing.diff`.

### 2.4 Screenshots

At least one terminal screenshot per system (`screenshots/`). Frame each on the moment that matters:
the routing summary counts; the discrepancy report with its exit code; the Contested section showing
both conflicting delivery numbers.

**Gate:** every rubric "Demonstrate Behavior" bullet has a named file.

---

## Phase 3 — Perturbations (rubric: *Stress-Test*, and "your own experiment earns more credit")

For each system, log **two** entries: the starter perturbation (baseline, proves the documented
behavior) and an **original** one (earns the extra credit the instructions call out). Record the
prediction *before* running — that's what the log's "What I predicted" field is for, and an honest
wrong prediction is more informative than a retrofitted right one.

### System 1
- **Starter:** run `pytest tests/test_us01_retry.py -v`, find the test where a null required field
  escalates with **exactly one** API call; then blank a required field in a *copy* of a policy doc
  (never edit the bundled corpus) and run `policy-extractor extract` live.
- **Original — signal isolation.** The router fires on `confidence ∧ reviewer ∧ integration`. Craft
  three copies of one policy, each perturbed to trip exactly one signal:
  (a) an internally contradictory endorsement limit (trips **integration**),
  (b) a subtly altered premium that the source text contradicts (trips **reviewer** disagreement),
  (c) a genuinely ambiguous/garbled field (drops **confidence**).
  Run all three. The result is a truth table mapping perturbation → firing signal → routing decision,
  answering reflection 1b with evidence instead of inference. This is the strongest original
  experiment available in the whole capstone.

### System 2
- **Starter:** contrast `income_sum_mismatch.txt` (flagged) with `appraisal_informal_sqft.txt` (clean).
- **Original — tolerance boundary probe.** `DEFAULT_TOLERANCE_USD = 1.00`. Make copies of an income
  document with the stated total off by **$0.50**, **$0.99**, **$1.00**, and **$1.50**, run each with
  `--mode record`, and record where the validator flips from `consistent` to a discrepancy. This turns
  a magic constant in `config.py` into a measured, documented operating characteristic — and surfaces
  whether the comparison is `<` or `<=` at the boundary.

### System 3
- **Starter:** run with and without `--simulate-timeout` and compare the Incomplete section.
- **Original — undated / triple-conflict claim.** Add a copy of the news corpus with (a) a claim whose
  date is stripped and (b) a *third* on-time-delivery figure from a fourth source. Two questions the
  system's design implies but never demonstrates: does an undated claim get excluded, downgraded, or
  silently treated as current? And does Contested hold three values or collapse to two? Whatever
  happens is a real finding for reflection 3c.

**Gate:** `perturbation-log.md` filled with six entries, each with change / command / prediction /
observed output line / contrast with unperturbed.

---

## Phase 4 — Reflection brief (rubric: *every prompt answered, every answer cited*)

Fill `reflection-brief.md` end to end. Discipline for every answer:

1. Quote a literal value, file name, or log line from the pack.
2. Name the artifact path it came from.
3. Then explain the mechanism.

Specific traps to get right:
- **1a** — the point is *one* API call. Retrying a `missing_source` failure is futile: the information
  is absent from the document, so no reformulation recovers it; retrying burns latency and budget and,
  worse, pressures the model toward invention. Escalation is the correct terminal state.
- **1c** — the aggregate Brier looks fine while `umbrella/exclusions` is 0.00 accurate at 0.93
  confidence. Slicing catches a *concentrated* failure that averaging dilutes.
- **2a** — two different guarantees: tool-use schema enforcement makes output *well-formed*
  (right shape, right types); the consistency validator makes it *coherent* (numbers agree). Schema
  can't catch a valid-but-wrong number; the validator can't catch a malformed response it never
  receives. Name one blind spot for each.
- **2b** — cite the nullable-union schema choice that *permits* `null`, plus the prompt rule that
  instructs "silent document → null." The schema makes honesty expressible; the prompt makes it
  preferred.
- **3a** — quote both numbers, both sources, both dates. The reader is better served because
  reconciling would erase the *disagreement itself*, which is the actionable signal.
- **4a/4b/4c** — the synthesis section is its own rubric line. Pick one concrete moment, one system,
  and one pattern you'd actually reach for, plus what you'd instrument.

**Stand-out:** answer 4c with an explicit instrumentation list — the metrics and alert thresholds
you'd ship (sliced calibration by segment, escalation rate, reviewer-disagreement rate, source
availability, discrepancy rate) — not just a pattern name.

---

## Phase 5 — Package & index

- `evidence-index.md` — **stand-out.** A table mapping every rubric bullet → the exact file and line
  range that satisfies it. The rubric's one hard rule is "a reviewer should be able to open any
  artifact you cite and find the exact value." An index makes that a two-second lookup instead of a
  hunt, and it doubles as a self-audit: any empty row is a gap found before submission.
- `run_all.sh` — **stand-out.** One script that rebuilds the entire evidence pack from a clean
  checkout. Reproducibility is the subject of the course; shipping a reproducible pack rather than
  merely describing one is the thesis applied to the submission itself.
- Final self-audit pass against all four rubric PDFs, then `zip` the folder.

**Gate:** every rubric row in `evidence-index.md` has a file + line.

---

## Phase 6 — The Primer (final deliverable)

`PRIMER.md` — a complete teaching document covering this capstone **and all eleven exercises** across
the three course projects. Every concept gets two passes: a **plain-English** explanation (analogy,
why it matters, what breaks without it) and an **engineering** explanation (the code, the types, the
failure modes, the tradeoffs).

Planned structure:

1. **The thesis** — why "evaluate the output, don't trust the model's word" is the organizing idea;
   the difference between a demo and a system you can be on call for.
2. **Core vocabulary** — extraction, schema, tool use / forced `tool_choice`, validation, retry
   classes, escalation, HITL routing, confidence vs. correctness, calibration, Brier score,
   stratified sampling, provenance, corroboration, conflict annotation, graceful degradation,
   observability vs. monitoring. Each: plain English first, then precise definition.
3. **Project 1 — Mortgage extraction** (4 exercises): resilient schema design (nullable unions,
   enum + `other` spillover, per-type `required`), two-pass classify-then-extract with forced
   `tool_choice`, extractor system prompt + normalization rules, cross-field math consistency.
   Includes the `calculated_monthly_total → None` vs `0.0` design note — a perfect miniature of the
   whole course.
4. **Project 2 — Policy pipeline** (4 exercises): retry with error feedback and the
   recoverable/irrecoverable split, batch + SLA with the dry-run sample gate, independent review and
   the within-policy integration pass, deterministic HITL routing + stratified spot-check +
   calibration.
5. **Project 3 — Supply-chain synthesis** (3 exercises): the one `Claim` shape, four heterogeneous
   readers, the shared vector store as agent memory, synthesis into
   Well-Established / Contested / Incomplete, and the resilient coordinator's timeout path.
6. **Cross-cutting patterns** — the five that recur: *make absence expressible*, *validate what the
   schema can't*, *classify failures before reacting*, *slice every aggregate*, *degrade, don't abort*.
7. **Diagrams** — per-system data-flow diagrams and a decision-flow diagram for the router
   (visual + code, per your stated learning preference).
8. **Anti-patterns and pitfalls** — the specific ways each of these goes wrong in production.
9. **Self-check questions** with answers, keyed to the reflection brief prompts.
10. **Applying it** — how to port these patterns to a new domain, and what to instrument day one.

Optionally publish the primer as a browsable HTML artifact as well, so it's readable outside the repo.

---

## Execution order

```
Phase 0 (supply-chain venv in background, others in parallel)
   └→ Phase 1 (verify)  ──┐
   └→ Phase 2 (behavior) ─┤
   └→ Phase 3 (perturb)  ─┴→ Phase 4 (reflection, needs all artifacts)
                              └→ Phase 5 (index + package)
                                   └→ Phase 6 (primer)
```

Phases 1–3 per system can interleave; Phase 4 cannot start until the artifacts it must cite exist.

## Risks

| Risk | Mitigation |
|---|---|
| torch/chromadb install is slow or fails | start it first, in the background; starter venv at `01-claim-readers/starter/.venv` is a known-good reference |
| Live pipeline run costs / rate limits | small corpus (10 docs); capture the offline test substitute too, so the pack is complete either way |
| Perturbations mutate the bundled corpus | always copy to a scratch dir; never edit `data/` or `fixtures/` in place; `git status` clean check after each phase |
| Live model output drifts from recorded fixtures | that's a *finding*, not a failure — record the diff and discuss it in the reflection |
