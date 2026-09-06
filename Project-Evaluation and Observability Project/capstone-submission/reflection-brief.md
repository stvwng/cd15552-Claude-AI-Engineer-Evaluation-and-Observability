# Reflection Brief — Evaluation and Observability Capstone

**Name:** Steve Wang
**Date:** 2026-09-05

> Every quoted value below is copied from an artifact in this evidence pack; the file is named
> alongside each one.

---

## 0. Environment

| Field | Value |
|---|---|
| OS & version | macOS 26.5.2 (build 25F84), Darwin 25.5.0, arm64 |
| Python version | 3.12.3 |
| Date run | 2026-09-05 (captures timestamped UTC in each artifact) |
| Ran any system live? (which) | **All three.** System 1's pipeline ran live end-to-end; System 2 ran live via `RecordingClient(mode="record")` into a throwaway cache; System 3 ran live with `AnthropicNewsExtractor`. Each system was **also** run offline with `ANTHROPIC_API_KEY` unset, so the pack contains both paths. |

Full detail, including `pip freeze` per venv and the git revision under test
(`d5951cc0912a96b409523841280e07b4372a78b5`), in `environment.txt`.

---

## 1. Validated, routed pipeline

| Evidence | Value |
|---|---|
| Passing test count | **45 passed, 3 skipped** offline; **48 passed** live (the 3 `@pytest.mark.live` tests execute) — `01-policy-pipeline/tests.txt` |
| Routing output file | `01-policy-pipeline/routing_decisions.json` (9 records) |
| auto_approve / human_review / spot_check counts | **0 / 8 / 1** — plus 1 escalation, so 10 documents in, 9 routed. `01-policy-pipeline/pipeline-run.txt` |

**1a. Retry boundary.** From your perturbation run (a required field removed), paste the escalation
record. How many API calls did the system make, and why is retrying a futile case worse than
escalating it?

> From `perturbations/system1/A-perturbed-premium-blanked.json`:
>
> ```json
> { "kind": "escalation",
>   "category": "missing_source",
>   "detected_pattern": "premium_amount_absent",
>   "field": "premium_amount",
>   "policy_id": "POL-2025-001-PERTURBED",
>   "reason": "Field 'premium_amount' returned null — the source document does not contain this
>              information. Retry is futile; escalate to human review." }
> ```
>
> **Exactly one API call**, despite `--max-retries 3`. `A-perturbed-premium-blanked.stderr` contains a
> single `HTTP Request: POST https://api.anthropic.com/v1/messages` line, followed immediately by
> `validation_failed`. The unit test pins the same invariant at
> `tests/test_us01_retry.py:360` — `assert client.call_count == 1  # no further API call`.
>
> Retrying is worse than escalating for three reasons, in increasing order of severity. The cheap one
> is cost and latency: three round trips to learn what the first one established. The structural one
> is that retry-with-error-feedback works by *appending the validation error to the conversation* —
> it is a mechanism for correcting a misreading, and there is nothing to correct here. The document
> genuinely does not contain a premium. No reformulation makes absent information present.
>
> The severe one is what the retry loop is actually asking the model to do. The feedback message says
> "this field came back null, try again." A model that complied on attempt two would have to produce
> a number that is not in the document. **The retry loop, applied to a `missing_source` failure, is a
> machine for pressuring the model into fabrication** — and a fabricated premium arrives with the same
> shape, the same type, and often the same confidence as a real one. The system would have converted
> a detectable gap into an undetectable error. Escalation is not a fallback here; it is the only
> correct terminal state, and the validator's three-way split (`format` / `consistency` /
> `missing_source`) exists precisely so the loop can tell the difference before it acts.

**1b. Reading the router.** Pick one `human_review` record from your routing output. Which of the
three signals (confidence, reviewer, integration) sent it to a human? If you had trusted the model's
confidence alone, what would have happened?

> **POL-2025-002**, from `01-policy-pipeline/routing_decisions.json`:
>
> ```json
> { "policy_id": "POL-2025-002",
>   "policy_type": "auto",
>   "decision": "human_review",
>   "reason": "reviewer_disagreement=['coverage_limit', 'deductible', 'endorsements']",
>   "fields_below_threshold": [],
>   "integration_failures": [],
>   "reviewer_disagreements": ["coverage_limit", "deductible", "endorsements"],
>   "confidence_summary": { "coverage_limit": 0.95, "deductible": 0.95, "endorsements": 0.95,
>                           "exclusions": 0.95, "policy_type": 1.0, "premium_amount": 1.0 } }
> ```
>
> The **reviewer** signal alone. Every confidence is 0.95 or above against a 0.90 threshold, so
> `fields_below_threshold` is empty; `integration_failures` is empty. On confidence alone this record
> auto-approves. A second model, shown the raw document and the proposed extraction but *nothing* from
> the extractor's prompt or tool-call history, disagreed on three of six fields.
>
> Across the whole run this is not an isolated case. From `perturbations/system1/D-signal-dominance.txt`:
>
> | signal | fired on | rate |
> |---|---|---|
> | reviewer | 8 / 9 | 89% |
> | confidence | 1 / 9 | 11% |
> | integration | 0 / 9 | 0% |
>
> **On 7 of 9 records the reviewer was the only signal that fired.** Trusting confidence alone would
> have auto-approved 8 of 9 records instead of 1 — it would have shipped 7 records the system
> considered unsafe, at a stated confidence of 0.95 and above.
>
> The counterfactual sharpens it: deleting the confidence signal changes the outcome for **zero**
> records; deleting the reviewer signal drops `human_review` from 8 to 1. On this corpus the router is
> effectively a reviewer-only router. Self-reported confidence is contributing almost nothing, which
> is the empirical form of the argument for not gating on it.

**1c. Where the aggregate lies.** Run the calibration snippet. Quote the one cell whose accuracy lags
its confidence, plus the overall figure. What does slicing by `policy_type × field` catch that a
single number hides?

> From `01-policy-pipeline/calibration-report.txt`:
>
> ```
> auto      premium_amount  n=3 conf=0.95 acc=1.00 brier=0.003
> home      deductible      n=1 conf=0.90 acc=1.00 brier=0.010
> umbrella  exclusions      n=2 conf=0.93 acc=0.00 brier=0.865
> OVERALL brier=0.291
> ```
>
> The offending cell is **`umbrella / exclusions`: `conf=0.93`, `acc=0.00`, `brier=0.865`.** It states
> 93% confidence and is wrong every single time. The aggregate is `0.291` — poor, but the kind of poor
> that reads as "needs tuning," not "one whole category is broken."
>
> The mechanism is dilution. Four well-calibrated samples (Brier 0.003 and 0.010) are averaged with two
> catastrophic ones (0.865), and the mean lands in unremarkable territory. Nothing about `0.291`
> suggests a *concentrated* failure; it is equally consistent with every cell being mediocre, which is
> a completely different problem with a completely different fix.
>
> Slicing changes the question from *how are we doing* to *where are we failing*, and only the second
> is actionable. `umbrella / exclusions` names a policy type and a field — a specific prompt, a
> specific set of documents, a specific reviewer check to add. It also identifies the danger zone:
> high confidence plus zero accuracy is the worst possible combination, because it is exactly the
> configuration that sails through a confidence gate. A cell that was wrong at *low* confidence would
> have been routed to a human anyway.
>
> The failure is invisible in the aggregate for a structural reason worth stating: **rare segments are
> underweighted in an average by definition, and rare segments are where models are worst.** The two
> facts compound. This is also why the spot-check sampler is stratified — see
> `01-policy-pipeline/sampler-seed-probe.txt`, where a naive `floor(10%)` sample draws **zero** records
> from the `umbrella` (n=3) and `other` (n=1) strata, auditing nothing in precisely the categories this
> calibration report flags as broken. The shipped `max(1, ceil(...))` rule guarantees every non-empty
> stratum is covered.

---

## 2. Schema-enforced two-pass extraction

| Evidence | Value |
|---|---|
| Passing test count | **25 passed** (`02-mortgage-extraction/tests.txt`; the solution README says 28 — the suite as shipped collects 25, evidenced by `--collect-only` in the same file) |
| Document run | `fixtures/documents/income_sum_mismatch.txt`, `income_missing_bonus.txt`, `appraisal_informal_sqft.txt` |
| Classified type | `income_verification` (first two), `appraisal` (third) — from the `-v` logs |

**2a. Two guarantees.** Paste your discrepancy-run output. Tool use already forces valid JSON, yet the
validator still catches a bad sum. Why are these two different guarantees? Name one error each cannot
catch.

> From `02-mortgage-extraction/discrepancy-run.txt`:
>
> ```
> mortgage_extractor.pipeline: classify: model=claude-haiku-4-5-20251001 in=1612 out=96 type=income_verification
> mortgage_extractor.pipeline: extract:  model=claude-haiku-4-5-20251001 in=3771 out=199 tool=extract_income_verification
> ```
> ```json
> "validation": {
>   "consistent": false,
>   "discrepancies": [
>     { "field": "total_monthly_income", "calculated": 9642.17, "stated": 10892.17, "delta": -1250.0 }
>   ] }
> ```
> exit `1`. The delta is exactly the $1,250.00 bonus: the document's own `TOTAL MONTHLY EARNINGS` line
> double-counts it. Both numbers are correctly extracted; the *document* is internally inconsistent.
>
> The two guarantees are about different properties. Tool use constrains **shape** — the right keys,
> the right types, parseable output. The consistency validator constrains **coherence** — whether the
> numbers, all individually well-formed, tell a story that can be true at once. Shape is a property of
> the response; coherence is a property of the world the response describes. No schema can express
> "these five floats must sum to that sixth float," and no arithmetic check can run on a response that
> failed to parse.
>
> **What each cannot catch:**
> - *Tool use cannot catch* the $1,250 discrepancy above. `{"base_monthly": 5416.67, ...,
>   "stated_monthly_total": 10892.17}` is perfectly schema-valid. Every field is a number, every
>   required key is present.
> - *The validator cannot catch* a fabricated value that happens to be arithmetically consistent. If
>   the model invented all five components *and* a stated total that matched their sum, `consistent`
>   would be `true` and the extraction would be entirely fictional.
>
> My live runs turned up the third failure class, which is the one that matters most and which
> **neither layer catches**. `perturbations/system2/live_vs_replay.py` ran the same document through
> three identical live calls (`02-mortgage-extraction/live-vs-replay.txt`):
>
> | attempt | model's `loan` / `property` | Pydantic |
> |---|---|---|
> | 1 | `"loan": {"amount": 0}`, `"property": {"address": "<UNKNOWN>", "property_type": "other"}` | **PASSED** |
> | 2 | both keys absent (correct — matches the fixture byte for byte) | PASSED |
> | 3 | `"loan": {"amount": null}`, `"property": {"address": null, ...}` | **REJECTED** |
>
> Attempt 3 was caught: `property.address  Input should be a valid string [input_value=None]`. Attempt
> 1 was not. This is an ADP paystub — it contains **no loan and no property at all** — and the model
> returned an `amount` of `0` and an address of `"<UNKNOWN>"`. Both are structurally impeccable and
> factually invented. Downstream, `amount: 0` is indistinguishable from a real $0 loan.
>
> So: **forced `tool_choice` did not make the output schema-conformant** (one call in three was
> rejected), and schema conformance did not make it true (a different call in three was fabricated).
> The three classes — malformed shape, arithmetic incoherence, plausible fabrication — need three
> different defenses, and the third one is not a schema at all. It is the independent review pass
> from System 1: a second model comparing the extraction against the source document.

**2b. Refusing to fabricate.** Run on a document missing a field. Paste that field's output. Why null
instead of an invented value? Point to the schema choice that allows it.

> From `02-mortgage-extraction/missing-field-run.txt` (`income_missing_bonus.txt`):
>
> ```json
> "income": {
>   "base_monthly": 5673.08,
>   "bonus_monthly": null,
>   "bonus_ytd": null,
>   "commission_monthly": null,
>   "overtime_monthly": null,
>   "other_monthly": null,
>   "stated_monthly_total": null }
> ```
>
> `bonus_monthly` is `null`. The paystub has no bonus line, and the extraction says so rather than
> guessing from the YTD column or inferring a plausible figure from base pay.
>
> **The schema choice that permits it** is the nullable union on every optional component in
> `mortgage_extractor/models.py` — `bonus_monthly: float | None`, not `float`. Because `None` is
> inside the type, "the document is silent" is *expressible*. A non-nullable `float` would leave the
> model no legal way to report absence: it must emit a number, and the only numbers available are
> invented ones.
>
> That is the whole mechanism, and it is worth stating plainly: **a required field is not a guarantee
> that the data exists, only a guarantee that something will be in that slot.** When the underlying
> fact is unavailable, a non-nullable field does not prevent the gap — it converts the gap into a
> fabrication and destroys the evidence that there ever was a gap.
>
> The design carries through to the aggregation. `perturbations/system2/null-vs-zero-probe.txt`
> confirms `Income.calculated_monthly_total` returns `None`, not `0.0`, when no components are set,
> and the validator guards with `if calculated is not None and stated is not None`. An income-less
> appraisal therefore *skips* the check rather than passing a vacuous `0.0 == 0.0` comparison. If the
> property returned `0.0`, a document where extraction silently failed would be indistinguishable from
> one that legitimately has no income — both would report `consistent: true`, one of them for the
> wrong reason.
>
> **The counter-example is in System 3**, and it is the sharpest lesson in this pack.
> `Claim.source_date` is declared `date`, not `date | None`, and is in the tool schema's `required`
> list. `data/meridian/news/ambiguous_meridian.txt` contains **no date anywhere** — it says "this
> quarter" and nothing more. The model cannot return null, so it invents: the live run dated three
> claims from that article `2024-01-01`; the recorded fixture dated the same article `2026-03-09`.
> Two runs, two different fabricated dates, for an article that has none
> (`03-supply-chain/live-vs-offline-briefing.txt`). Same principle, opposite outcome, decided entirely
> by whether one field was declared nullable.

**2c. Normalization.** Quote one field where the source text and extracted value differ in format
("about 2,400 sq ft" → `2400`). Why normalize at extraction time rather than downstream?

> From `02-mortgage-extraction/extract-run.txt`. Source document:
>
> ```
> Gross Living Area:   approximately 2,400 sq ft (above-grade finished)
> ```
>
> Extracted:
>
> ```json
> "gross_living_area_sqft": 2400
> ```
>
> Three transformations at once: the hedge `approximately` is dropped, the thousands separator is
> removed, and the unit moves out of the value and into the **field name** (`_sqft`). The result is an
> integer that arithmetic can touch. The same run also normalizes `$ 410,000` → `410000.0` and
> `Owner-Occupied` → the enum `primary_residence`.
>
> Normalizing at extraction time rather than downstream, for four reasons:
>
> 1. **The context is here and nowhere else.** Deciding that `2,400` means twenty-four hundred rather
>    than two-point-four requires knowing this is a US appraisal in square feet. The extractor has the
>    whole document; a downstream consumer has a lonely string. The same file contains `0.46 acres`
>    and `441 sq ft` — the unit is only recoverable in situ.
> 2. **It happens once instead of N times.** Every downstream consumer would otherwise write its own
>    parser, and they would disagree. The one that mishandles `approximately` becomes a bug nobody can
>    localize.
> 3. **It is the boundary where the type contract is enforced.** `gross_living_area_sqft: int | None`
>    is only meaningful if something guarantees an `int` arrives. Deferring normalization means
>    deferring the type, and the schema stops being load-bearing.
> 4. **Consistency checking depends on it.** The validator compares `calculated` against `stated`. It
>    cannot subtract `"about 2,400 sq ft"` from anything. Normalization is what makes the arithmetic
>    guarantee in 2a possible at all — an un-normalized pipeline cannot have a consistency validator.
>
> The honest cost: normalization is lossy. `approximately` was real information, and it is now gone —
> the schema has no `is_approximate` flag. For gross living area that is an acceptable trade; for a
> field where the hedge carries legal weight it would not be, and the right answer would be to keep
> both the normalized value and the raw span.

---

## 3. Multi-source synthesis

| Evidence | Value |
|---|---|
| Passing test count | **34 passed** — `03-supply-chain/tests.txt` |
| Briefing file | `03-supply-chain/briefing.md` (normal), `briefing-timeout.md` (source failure), `briefing-live.md` (live news extraction) |
| Section the conflict landed in | **Contested**, with ⚠️ ESCALATE |

**3a. Annotate, don't arbitrate.** Quote one conflicting-metric pair from your briefing — both values,
sources, dates. Give one way a reader is better served by the preserved conflict than by a single
reconciled number.

> From `03-supply-chain/briefing.md`:
>
> ```
> ## Contested
> ### on_time_delivery_rate  _[2 sources, conflicting]_  ⚠️ ESCALATE
> - escalation: high-impact metric is contested across sources
> - Reported values by source:
>     - 95.0 percent — supplier_audit (as of 2026-04-10)
>     - 78.0 percent — logistics     (as of 2026-04-05)
> ```
>
> Both values, both sources, both dates, no average. Note what a reconciled number would have to be:
> the mean is 86.5%, which **no source reported** and which describes no state of the world.
>
> The reader is better served because **the gap is the finding.** 95 is the supplier's self-assessment;
> 78 is what our own logistics data shows across 50 shipments (39 on time). Those are not two noisy
> measurements of one quantity — they are one party's claim and one party's audit of that claim, and a
> 17-point spread between them is a fact about the *supplier relationship*, not about delivery
> performance. It says the supplier's reporting is unreliable, or that the two are counting different
> things (promised-date resets? excluded lanes?). Averaging to 86.5% erases the only signal that
> matters and replaces it with a number that is wrong in a new way.
>
> Concretely: the action implied by "delivery is 86.5%" is a performance conversation. The action
> implied by "they claim 95, we measure 78" is an audit of their measurement methodology, and possibly
> a contractual one about reporting. A single reconciled number does not merely lose precision — it
> routes the reader to the wrong action.
>
> This is also the one part of the briefing that is completely stable across every run I made. The
> Contested section is byte-identical in the offline and live runs
> (`03-supply-chain/live-vs-offline-briefing.txt`) because both values come from deterministic readers
> — a JSON audit file and a CSV — while the news reader's output varied from 9 to 18 metrics between
> runs. The architecture puts the load-bearing conflict detection on parsers and confines the LLM to
> the one source that cannot be parsed otherwise.

**3b. Source goes dark.** Run with `--simulate-timeout`. Paste the part of the briefing showing the
failed source. How is "unreachable" handled differently from "nothing to report," and why does the run
still finish?

> From `03-supply-chain/briefing-timeout.md`:
>
> ```
> # Supply Chain Risk Briefing — Meridian
>
> > Sources unavailable: logistics unavailable (timeout)
> ...
> ## Incomplete
> ### late_shipment_count  _[missing source: timeout reading logistics]_
> - missing source: timeout reading logistics
>
> ### production_capacity_utilization  _[missing source: no source reported this metric]_  ⚠️ ESCALATE
> - escalation: high-impact metric has no usable source
> ```
>
> **The distinction is visible in those two adjacent entries.** Both are Incomplete; the annotations
> differ. `timeout reading logistics` means *we could not ask*. `no source reported this metric` means
> *we asked everyone and nobody knew*. Same section, different causes, different remedies: the first is
> retryable and the number probably still exists; the second is a coverage gap that no retry fixes and
> that needs a new source wired in. Collapsing both into a generic "missing" would discard the only
> information that says which action to take.
>
> The run finishes because the failure is modeled as a **value, not an exception**. `ReaderResult`
> carries `ok: bool` and an optional `FailureContext` (`failure_type`, `attempted`, `partial_results`,
> `alternatives`), so a dead source returns a result *describing* the failure instead of raising
> through the coordinator. Aborting would be strictly worse: three of four sources succeeded, and the
> audit, quality and news findings have nothing to do with a logistics outage. Throwing them away
> converts a partial answer into no answer.
>
> **The finding that concerns me most is what else changed.** `03-supply-chain/timeout-diff.txt`:
>
> ```
> normal:   ## Contested        ### on_time_delivery_rate _[2 sources, conflicting]_ ⚠️ ESCALATE
>                                   95.0% — supplier_audit (2026-04-10)
>                                   78.0% — logistics     (2026-04-05)
> timeout:  ## Well-Established ### on_time_delivery_rate _[single source only]_
>                                   95.0% — supplier_audit (2026-04-10)
>           ## Contested        _none_
> ```
>
> The contested metric was **promoted to Well-Established**. The disagreement was not resolved — the
> dissenting source went offline — and the value that survives is the supplier's own self-reported
> 95%, the optimistic one. The pessimistic 78% was ours. The Contested section now reads `_none_`, and
> the ⚠️ ESCALATE flag is gone.
>
> Graceful degradation is not free. Losing a source does not merely reduce coverage; **it can convert a
> known disagreement into false confidence, and here it does so in the reassuring direction.** The
> `_[single source only]_` badge and the header banner are the only things standing between this
> briefing and a reader who concludes on-time delivery is fine. My operational conclusion is that
> source availability is a *data-quality* metric, not an infrastructure one, and that a metric which
> was Contested last run and is Well-Established this run **because a source dropped out** deserves an
> alert of its own.

**3c. Dates as a guardrail.** Quote two claims about the same supplier with different dates. How does
requiring a date stop a time difference from reading as a contradiction?

> From `03-supply-chain/briefing.md`:
>
> ```
> ### defect_rate_ppm  _[corroborated across 2 sources]_
> - Reported values by source:
>     - 180.0 ppm — supplier_audit    (as of 2026-04-10)
>     - 190.0 ppm — internal_quality  (as of 2026-04-08)
> ```
>
> Two sources, two values, two days apart. Without dates, `180` and `190` are just two numbers in
> tension and a reader must guess whether that is disagreement or drift. With dates attached, the
> reader can see the measurements are two days apart and that a 10-ppm move over 48 hours on a
> ~185-ppm baseline is ordinary variation, not a dispute about a fact. The date converts an apparent
> contradiction into a time series, which is a different — and usually less alarming — object.
>
> The structural point is that `source`, `source_date` and `confidence` live on the `Claim` itself
> rather than being attached during synthesis. Provenance travels with the data through the vector
> store and out the other side, so attribution cannot be lost by a later step. Synthesis is
> deterministic Python, not an LLM call, which is why the docstring can say provenance preservation is
> *guaranteed rather than prompted*.
>
> **The guardrail has a hole, and I found it by running live.** Requiring a date only helps when the
> date is real, and `Claim.source_date` is declared `date`, not `date | None`, with `source_date` in
> the tool schema's `required` list. `data/meridian/news/ambiguous_meridian.txt` carries **no date at
> all** — `grep -inE 'date|20[0-9]{2}'` returns nothing; the article says "this quarter." The model
> cannot return null, so it fabricates one:
>
> ```
> live run:      > Meridian has missed payments to subcontractors. (industry_news, 2024-01-01)
> recorded run:  > A company named 'Meridian' is facing supplier financial distress ...
>                  (industry_news, 2026-03-09)
> ```
>
> Two runs, two different invented dates, neither in the source
> (`03-supply-chain/live-vs-offline-briefing.txt`). And the failure is *anti-correlated with safety*:
> a fabricated `2024-01-01` makes current financial-distress reporting look two years stale, so a
> reader triaging by recency deprioritizes the single most urgent item in the briefing — one already
> flagged ⚠️ ESCALATE for ambiguous supplier identity.
>
> So the honest answer to this question is two-sided. Requiring a date is the right design: it is what
> lets 180-vs-190-ppm read as drift rather than conflict. But *requiring* it without making absence
> expressible turns a missing date into a manufactured one, and a manufactured date is worse than no
> date because it is indistinguishable from evidence. The fix is one type change and one prompt
> sentence: `source_date: date | None`, instruct the model to return null when the article carries no
> publication date, and render those claims as `(industry_news, date not stated)`.

---

## 4. Synthesis

**4a. One principle.** Name the single moment in your runs (system + artifact) where *evaluate the
output, don't trust the model's word* most clearly caught something a trusting design would have
shipped.

> **System 2, attempt 3 of `02-mortgage-extraction/live-vs-replay.txt`.**
>
> Three identical live calls — same model, same prompt, same document. Attempt 3 returned:
>
> ```json
> "loan":     { "amount": null, "term_months": null, ... },
> "property": { "address": null, "property_type": null, ... }
> ```
>
> and Pydantic rejected it:
>
> ```
> property.address       Input should be a valid string [type=string_type, input_value=None]
> property.property_type Input should be a valid string [type=string_type, input_value=None]
> loan.amount            Input should be a valid number [type=float_type,  input_value=None]
> ```
>
> I chose this moment because of what surrounds it. The call used **forced `tool_choice`** — the
> mechanism whose entire purpose is to guarantee schema-conformant output. It did not. One call in
> three produced input the schema rejects. A design that trusted `tool_choice` and skipped the
> validation layer would have passed an all-null property object downstream into underwriting.
>
> What makes it decisive rather than merely illustrative is attempt 1 in the same batch: fabricated
> `{"amount": 0}` and `{"address": "<UNKNOWN>"}` on a document containing neither a loan nor a
> property, and Pydantic **passed** it. So within three calls I have both halves of the argument — the
> guarantee failing, and the backstop itself proving insufficient against a well-formed lie. One
> validation layer is not enough; it is the *floor*, and the reason System 1 puts an independent
> reviewer above it.

**4b. Confidence ≠ correctness.** Pick the system where this mattered most, and explain why using
something you observed.

> **System 1**, in two artifacts that say the same thing from opposite directions.
>
> *Confidence being high and wrong.* `01-policy-pipeline/calibration-report.txt`:
> `umbrella exclusions n=2 conf=0.93 acc=0.00 brier=0.865`. The model is 93% sure and 0% right. If
> confidence tracked correctness at all, 0.93 would mean roughly nine correct in ten; here it means
> none in two. And the aggregate — `OVERALL brier=0.291` — conceals it, because two catastrophic
> samples average against four good ones into something that reads as merely unimpressive.
>
> *Confidence being high and irrelevant.* `perturbations/system1/D-signal-dominance.txt`: across nine
> live records, the confidence signal fired on **1 of 9**; the independent reviewer fired on **8 of
> 9**; on **7 of 9** the reviewer was the *only* signal. Removing confidence from the router changes
> the outcome for **zero records**. Removing the reviewer drops human review from 8 to 1. Those seven
> records carried confidences of 0.95 and above — a confidence-gated router auto-approves every one of
> them.
>
> Put together: self-reported confidence was neither *calibrated* (the umbrella cell) nor *load-bearing*
> (the counterfactual). It is not a probability of correctness; it is a token the model emits about its
> own output, generated by the same process that produced the output and sharing all of its blind
> spots. That is the structural reason the router treats it as **one of three** inputs and why the two
> signals that actually caught things — a second model that never saw the first model's reasoning, and
> a deterministic cross-field check — are both *external* to the extraction. Independence is the
> property that makes a signal worth having, and self-reported confidence has none.

**4c. Apply it.** Describe a real workflow where an LLM pulls structured results from messy input.
Which pattern — validated retry with escalation, independent review with deterministic routing, or
provenance-preserving conflict annotation — would you reach for first, and what would you instrument
to know when it broke?

> **The workflow.** Vendor-security review intake. Prospective vendors return a completed security
> questionnaire plus attachments — a SOC 2 Type II report, a pen-test summary, sometimes a DPA — as
> PDFs of wildly varying quality. A reviewer extracts perhaps forty structured fields (SOC 2 scope and
> audit period, exceptions noted, encryption at rest and in transit, subprocessor list, breach
> notification SLA, data residency) into a risk register that gates procurement. It is high-volume,
> deeply tedious, and the failure mode is quiet: a wrong `breach_notification_hours` sits in the
> register for two years until it matters.
>
> **First pattern: independent review with deterministic routing.** Not validated retry, and the
> reason is what I observed rather than a preference. Retry-with-escalation only fires on failures a
> validator can *name* — malformed output, a null in a required field, arithmetic that doesn't
> reconcile. The errors that hurt here are none of those. `"breach_notification_hours": 72` is
> well-formed, in range, and internally consistent whether the contract says 72 hours, 72 business
> hours, or 24. That is attempt 1 of my live-vs-replay run exactly: structurally impeccable, factually
> invented, and invisible to every schema-shaped defense. Only a second pass comparing the extraction
> against the source document catches it — and in my run that pass was doing 89% of the work while
> confidence did 11% and the cross-field checks did 0%.
>
> Validated retry still goes in, underneath, precisely because System 1 taught me it is cheap and
> because the `missing_source` split is what stops "the SOC 2 doesn't state a residency" from becoming
> an invented residency. But it is the floor, not the primary defense. Conflict annotation earns its
> place too, in a specific spot: when the questionnaire answer and the SOC 2 report disagree, that gap
> is the finding — the same shape as 95%-vs-78%, one party's claim against the evidence — and
> averaging or preferring one source would destroy the signal that matters most.
>
> **What I would instrument**, and the run that taught me each:
>
> | Metric | Why | Learned from |
> |---|---|---|
> | Calibration **sliced by (document_type × field)**, Brier per cell, never aggregate alone | The overall number hid a cell at `conf=0.93 acc=0.00` | `calibration-report.txt` |
> | Per-signal firing rates + a monthly **counterfactual** (which signals still catch each record if one is removed) | A check that never fires is indistinguishable from a broken one; integration fired on 0/9 and I only know it works because I perturbed a document to trip it | `D-signal-dominance.txt` |
> | **Schema-rejection rate** on live tool calls, alerting on any sustained non-zero | Forced `tool_choice` gave me 1 malformed response in 3 | `live-vs-replay.txt` attempt 3 |
> | **Placeholder-value detector** — scan accepted extractions for `0`, `"<UNKNOWN>"`, `"N/A"`, epoch-ish dates in fields the source never mentioned | The class no schema catches; both fabrications I found were of this shape | attempt 1; `2024-01-01` |
> | Escalation rate split by category (`missing_source` vs `format` vs `consistency`) | A rising `missing_source` rate means the *documents* changed, not the model — a different fix entirely | `pipeline-run.txt` `pattern_summary` |
> | **Source availability as a data-quality metric**, plus an alert when a field moves from Contested to Well-Established *because a source dropped out* | The most alarming thing I found: a conflict silently became false confidence, in the optimistic direction | `timeout-diff.txt` |
> | Spot-check coverage **per stratum**, alerting on any stratum at zero | Naive `floor(10%)` sampling audits nothing in the rarest categories, which is where the bad calibration cell lives | `sampler-seed-probe.txt` |
> | Signal values logged **at decision time**, never re-derived | Two identical live runs, same seed, produced different reviewer verdicts; a re-derived "why" would be a different answer than the one the decision was made on | `seed-determinism.txt` |
>
> That last row is the one I did not expect going in and the one I would carry furthest. My router is a
> pure function and my sampler is seeded and reproducible — but both sit on top of a nondeterministic
> signal, and POL-2025-007 moved from `spot_check` to `human_review` between two runs of the identical
> command. **A deterministic system built on a nondeterministic input is only as reproducible as its
> inputs, and the only way to audit a past decision is to have recorded the values it was made from.**
