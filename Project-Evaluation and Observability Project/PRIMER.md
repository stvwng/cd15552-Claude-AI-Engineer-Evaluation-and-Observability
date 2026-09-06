# Primer — Evaluation and Observability for LLM Systems

A complete walkthrough of the three reference systems in this repository, the eleven exercises that
build them, and the ideas underneath. Written to be read once end-to-end and then used as a reference.

Every concept gets two passes:

- **In plain English** — the idea, an analogy, and what breaks without it. No code.
- **In engineering terms** — the types, the code, the failure modes, the tradeoffs.

Where a claim was verified by an actual run in this repo, the artifact is cited as
`capstone-submission/<path>`. Those are the moments the theory either held or didn't.

---

## Table of contents

1. [The thesis](#1-the-thesis)
2. [Core vocabulary](#2-core-vocabulary)
3. [Project 1 — Mortgage document extraction](#3-project-1--mortgage-document-extraction)
4. [Project 2 — Insurance policy pipeline](#4-project-2--insurance-policy-pipeline)
5. [Project 3 — Supply-chain multi-source synthesis](#5-project-3--supply-chain-multi-source-synthesis)
6. [Five cross-cutting patterns](#6-five-cross-cutting-patterns)
7. [Diagrams](#7-diagrams)
8. [Anti-patterns and pitfalls](#8-anti-patterns-and-pitfalls)
9. [What the runs actually proved](#9-what-the-runs-actually-proved)
10. [Self-check questions](#10-self-check-questions)
11. [Applying this to your own work](#11-applying-this-to-your-own-work)

---

## 1. The thesis

### In plain English

There is a large gap between an LLM feature that demos well and one you would agree to be paged for
at 3am.

The demo version works like this: you send a document to a model, ask for JSON back, and it comes
back looking right. You try five documents. All five look right. You ship it.

The production version has to answer a harder question: **when this is wrong, how will I know?**

That question is harder than it sounds, because LLM failures do not look like normal software
failures. A null-pointer exception announces itself. A crashed process announces itself. But a
language model that misreads a premium as $1,847.62 when the document says $1,874.62 returns a
perfectly well-formed number, with no error, no stack trace, and — this is the part that catches
people — often with high stated confidence. It fails **silently and plausibly**. A wrong answer and a
right answer are the same shape.

So the organizing principle of this whole course is one sentence:

> **Evaluate the output. Don't trust the model's word.**

Not because models are bad. Because "the model said so" is not evidence, and a system built on it has
no way to distinguish its good days from its bad ones.

Everything else follows from that. If you can't trust the model's word, you need *other* signals:
a schema that constrains shape, arithmetic that has to reconcile, a second model that never saw the
first one's reasoning, a human in the loop for the cases that matter, and enough logging that you can
answer "why did this record get approved?" six months later.

**The analogy.** Think about how a newspaper handles a story versus how a rumor spreads. A rumor is a
claim with no attribution — you cannot check it, you cannot date it, and if two versions disagree you
have no way to adjudicate. A newspaper attaches a source and a date to every claim, runs it past an
editor who did not write it, prints corrections when it gets things wrong, and keeps the notes. Same
information, radically different trustworthiness — and the difference is entirely in the *process
around* the claim, not the claim itself.

These three systems are that process, applied to model output.

### In engineering terms

Three properties, and each of the three projects is mostly about one of them.

| Property | Question it answers | Project |
|---|---|---|
| **Evaluation** | Is this output correct, and how would I measure that at scale? | 1 — schema, validation, consistency |
| **Reliability** | What happens when something fails — the model, a source, the network? | 2 — retry classes, escalation, batch, HITL routing |
| **Observability** | Can I reconstruct *why* the system did what it did? | 3 — provenance, conflict annotation, graceful degradation |

They are not separable in practice. The routing layer in Project 2 is a reliability mechanism whose
output (`routing_decisions.json`) is an observability artifact, and whose thresholds are set by an
evaluation artifact (the calibration report). But the split is a useful way to hold them.

**The core distinction to internalize, stated precisely:**

```
well-formed  ≠  valid  ≠  correct
```

- **Well-formed** — parses; right keys, right types. Enforced by tool-use schemas.
- **Valid** — satisfies domain invariants. Numbers reconcile, enums are legal, required fields
  present. Enforced by validators.
- **Correct** — matches reality. **Not enforceable by any local check.** Only an independent
  comparison against the source, or a human, gets you here.

Most LLM production incidents live in the gap between *valid* and *correct*, and that gap is where
the interesting engineering is. A system that only enforces well-formedness has one layer of defense
against a three-layer problem.

---

## 2. Core vocabulary

Read this section once, then use it as a lookup. Each term gets the plain-English version first.

### Extraction

**Plain English.** Turning messy human documents — a scanned paystub, a policy declaration page, a
news article — into tidy rows and columns a program can use. The messy part is that humans write
"about 2,400 sq ft" and "$ 1,847.62" and "see attached Schedule A," and a database wants `2400`,
`1847.62`, and some honest representation of "the schedule wasn't attached."

**Engineering.** A function `str -> StructuredRecord`, implemented as an LLM call constrained by a
tool schema, followed by parsing and validation. The hard parts are not the happy path; they are
absence, ambiguity, and normalization.

### Schema

**Plain English.** The shape of the answer, agreed in advance. Like a form with labeled boxes: this
box holds a number, that one holds a date, this one may be left blank. The design question that
matters most is *which boxes are allowed to be blank* — because a box that must be filled will get
filled, whether or not the information exists.

**Engineering.** A JSON Schema attached to a tool definition. The Anthropic API validates `tool_use`
input against it before returning. Three distinct idioms, often confused:

```python
# 1. "The key may be absent entirely."
#    -> leave it out of `required`
{"properties": {"hoa_dues_monthly": {"type": "number"}}, "required": []}

# 2. "The key will be present, but its value may be unknown."
#    -> nullable union
{"bonus_monthly": {"type": ["number", "null"]}}

# 3. "The value space will grow over time."
#    -> enum + "other" + sibling detail field
{"property_type":        {"type": "string", "enum": [...,"other"]},
 "property_type_detail": {"type": ["string", "null"]}}
```

Getting these wrong is the single most common source of fabrication. See
[§3.1](#31-exercise-1--design-the-resilient-extraction-schema).

### Tool use / structured output

**Plain English.** Instead of asking the model to "reply with JSON" and hoping, you hand it a
function signature and it fills in the arguments. The API enforces the argument types.

**Engineering.** You pass `tools=[...]` and read the `ToolUseBlock` from `response.content`:

```python
blocks = [b for b in response.content if isinstance(b, ToolUseBlock)]
data = blocks[0].input          # a dict, already schema-checked
```

**Never** parse `response.content[0].text`. The text block is prose; the tool block is data.

**A caveat this repo's own runs established:** schema enforcement is strong but *not* absolute. In
`capstone-submission/02-mortgage-extraction/live-vs-replay.txt`, three identical live calls produced
one response that Pydantic rejected outright (`property.address  Input should be a valid string
[input_value=None]`). Treat the schema as a strong filter, not a guarantee, and keep a validation
layer behind it.

### `tool_choice` — forced vs. any

**Plain English.** Two different instructions. "Use *this* tool" leaves the model no decision. "Use
*one of* these tools" makes it choose — which is only meaningful if you give it a real choice,
including an escape hatch for "I can't do this."

**Engineering.**

```python
tool_choice={"type": "tool", "name": "classify_document"}  # forced: exactly this tool
tool_choice={"type": "any"}                                # any registered tool, model picks
tool_choice={"type": "auto"}                               # tool or prose, model picks
```

`{"type": "any"}` with a single registered tool is just a verbose forced call. It becomes useful when
you register a genuine alternative — in this repo, `flag_for_review`, which lets the model decline
rather than guess. **Giving a model a legitimate way to refuse is a design tool**, and it is the same
insight as making a field nullable, one level up.

### Validation

**Plain English.** Checking the answer against rules the schema can't express. "This number must be
positive." "These five line items must add up to that total." Shape-checking is spellcheck;
validation is proofreading.

**Engineering.** A pure function `Record -> Error | None`, run after parsing. Critically, it should
**classify** failures, not just detect them — the classification is what lets the caller decide
between retry and escalate. See [§4.1](#41-exercise-1--retry-with-error-feedback).

### Retry with error feedback

**Plain English.** When the answer is wrong in a fixable way, show the model exactly what it produced
and exactly why it was rejected, then ask again. Not "try harder" — "here is your previous answer,
here is the specific problem with it."

**Engineering.** Append the prior attempt and the validator's message to the next request:

```
<prior_attempt index="1">
  <extraction>{'premium_amount': -1847.62, ...}</extraction>
  <validation_error field="premium_amount" category="format" detected_pattern="negative_premium">
    premium_amount is -1847.62, which is negative. ...
  </validation_error>
</prior_attempt>
```

The verbatim prior value matters. "Your answer was invalid" gives the model nothing to work with.

### Recoverable vs. futile failure

**Plain English.** Some mistakes are misreadings — the information is there and the model got it
wrong. Others are absences — the information genuinely isn't in the document. Retrying the first kind
can work. Retrying the second kind cannot, and worse, it *pressures the model to make something up*.

**Engineering.** The three-way split in `policy_extractor/validator.py`:

| Category | Meaning | Action |
|---|---|---|
| `format` | Well-formed but illegal (negative premium) | **retry** with feedback |
| `consistency` | Individually fine, mutually contradictory | **retry** with feedback |
| `missing_source` | The document does not contain it | **escalate immediately**, zero further calls |

This is the most transferable single idea in the course. Verified in
`capstone-submission/perturbations/system1/A-perturbed-premium-blanked.stderr` — exactly one API call
despite `--max-retries 3`.

### Escalation

**Plain English.** Handing a case to a human, on purpose, as a correct outcome. Not a crash, not a
fallback — a designed terminal state.

**Engineering.** A distinct return type, not an exception:

```python
ExtractionOutcome = PolicyExtraction | RetryFutileEscalation
```

A union type forces every caller to handle both branches. An exception lets callers ignore the case
until it happens in production.

### Human-in-the-loop (HITL) routing

**Plain English.** Deciding which results a person needs to look at. You can't review everything —
that defeats the purpose — and you can't review nothing. The decision must be *rule-based and
inspectable*, not "the model seemed unsure."

**Engineering.** A pure function of independent signals:

```python
def route_extraction(*, extraction, review, integration_findings, threshold=0.90) -> RoutingDecision
```

Deterministic and side-effect-free, so the same inputs always yield the same decision and the
decision can be unit-tested without the API.

### Confidence vs. correctness

**Plain English.** When a model says it is 93% sure, that is not a probability. It is another token
it generated, produced by the same process that produced the answer, sharing all the same blind
spots. A model that misreads a document confidently misreads its own confidence too.

**Engineering.** Verified twice in this repo's runs:

- *Not calibrated*: `umbrella/exclusions  conf=0.93  acc=0.00  brier=0.865`
  (`capstone-submission/01-policy-pipeline/calibration-report.txt`) — 93% sure, wrong every time.
- *Not load-bearing*: across 9 live records the confidence signal fired on 1; removing it from the
  router changed **zero** outcomes, while removing the independent reviewer dropped human review from
  8 to 1 (`capstone-submission/perturbations/system1/D-signal-dominance.txt`).

Use self-reported confidence as *one* input among several. Never as the gate.

### Calibration and the Brier score

**Plain English.** Calibration asks: when the model says 90%, is it right about 90% of the time? The
Brier score is one number for how far off it is — the average squared distance between what it
claimed and what actually happened. Zero is perfect. 0.25 is what you get by always saying "50/50."

**Engineering.**

```python
brier = mean((predicted_confidence - actual_outcome) ** 2)   # actual ∈ {0.0, 1.0}
```

The critical practice is **slicing**. A single aggregate hides concentrated failures, because rare
segments are underweighted in an average by definition — and rare segments are where models are
worst. The two facts compound:

```
auto      premium_amount  n=3 conf=0.95 acc=1.00 brier=0.003
home      deductible      n=1 conf=0.90 acc=1.00 brier=0.010
umbrella  exclusions      n=2 conf=0.93 acc=0.00 brier=0.865   <-- broken
OVERALL brier=0.291                                            <-- looks merely mediocre
```

An aggregate answers *how are we doing*. A slice answers *where are we failing*. Only the second is
actionable.

### Stratified sampling

**Plain English.** If you spot-check 10% of approved work at random, the rare categories get checked
almost never. Stratified sampling checks a fixed share *of each category*, so the rare ones are still
covered.

**Engineering.** `max(1, ceil(sample_pct * n))` per stratum. The `max(1, ...)` is the whole point.
Measured in `capstone-submission/01-policy-pipeline/sampler-seed-probe.txt`:

| stratum | n | naive `floor(10%)` | shipped `max(1, ceil(10%))` |
|---|---|---|---|
| auto | 20 | 2 | 2 |
| home | 12 | 1 | 2 |
| umbrella | 3 | **0** | 1 |
| other | 1 | **0** | 1 |

Naive sampling audits *nothing* in the two rarest categories — which is exactly where the calibration
report says the model is broken.

### Provenance

**Plain English.** Where a fact came from, and when. "On-time delivery is 95%" is nearly useless.
"The supplier's own audit, dated 2026-04-10, says 95%" is a fact you can act on — you know who is
making the claim and how fresh it is.

**Engineering.** Attach source and date to the *data structure*, not to the rendering layer, so it
cannot be lost by an intermediate step:

```python
class Claim(BaseModel):
    model_config = ConfigDict(frozen=True)
    claim: str
    evidence: str
    source: str
    source_date: date
    confidence: float = Field(ge=0.0, le=1.0)
    metric_id: str
    value: float | None = None
```

Frozen, so provenance cannot be mutated downstream.

### Conflict annotation (vs. arbitration)

**Plain English.** When two sources disagree, you can pick one, average them, or show both. Showing
both is usually right, because *the disagreement is itself the finding*. Averaging 95% and 78% gives
you 86.5% — a number no source reported, describing no state of the world, and quietly destroying the
information that the supplier's self-report doesn't match your own measurements.

**Engineering.** Keep every value with its attribution; never emit a single reconciled figure.

```
### on_time_delivery_rate  _[2 sources, conflicting]_  ⚠️ ESCALATE
    - 95.0 percent — supplier_audit (as of 2026-04-10)
    - 78.0 percent — logistics     (as of 2026-04-05)
```

### Graceful degradation

**Plain English.** When one input dies, finish the job with what's left and say plainly what's
missing. Don't crash, and don't quietly pretend the missing part never existed.

**Engineering.** Errors as values, not exceptions:

```python
class ReaderResult(BaseModel):
    source: str
    ok: bool
    claims: list[Claim] = Field(default_factory=list)
    error: FailureContext | None = None
```

**With an important caveat this repo's runs surfaced**, covered in
[§5.3](#53-exercise-3--the-resilient-coordinator): degradation is not neutral. Losing a source can
convert a *known disagreement* into *false confidence*.

### Observability vs. monitoring

**Plain English.** Monitoring tells you the system is sick. Observability lets you find out why
without shipping new code. For LLM systems the question is almost always "why did this specific
record get this specific treatment?" — and you can only answer it if you *recorded the reasons at the
time*.

**Engineering.** Log the **signal values at decision time**, not just the decision, and never
re-derive them later. This repo demonstrates why: two identical live runs with the same `--seed 42`
produced different reviewer verdicts, and one record moved from `spot_check` to `human_review`
(`capstone-submission/01-policy-pipeline/seed-determinism.txt`). A re-derived explanation would be a
*different* explanation than the one the decision was actually made on.

---

## 3. Project 1 — Mortgage document extraction

**Scenario.** You are the senior AI engineer at Meridian Home Lending. Underwriters receive loan
applications, appraisals and paystubs as OCR'd PDFs. They need structured data they can trust — where
"trust" specifically means *knowing the difference between "the document said $0" and "the document
didn't say."*

**Arc.** Schema → orchestration → prompt → validation. Each exercise adds one layer, and the layers
are ordered by how hard they are to change later: the schema is the contract everything else depends
on, so it comes first.

```
document text
   │
   ├─ PASS 1: classify_document        tool_choice = forced
   │            └─> DocumentType {loan_application | appraisal | income_verification | other}
   │                     └─ OTHER ─────> UnsupportedDocumentTypeError (short-circuit)
   │
   ├─ PASS 2: extract_<doc_type>       tool_choice = "any"
   │          + flag_for_review              (escape hatch)
   │            └─> MortgageExtraction (Pydantic)
   │
   └─ validate()  ──> ValidationReport{consistent, discrepancies[]}
                       exit 0 if consistent, 1 if not
```

### 3.1 Exercise 1 — Design the resilient extraction schema

**Files:** `mortgage_extractor/schema.py`, `mortgage_extractor/tools.py`
**Verify:** `pytest tests/test_us01_schema.py` (5 tests)

#### In plain English

This exercise is about one deceptively simple question: **which fields is the model allowed to leave
blank?**

Here is why it matters more than it sounds. Suppose you build a form where "bonus income" is a
required field. A paystub arrives with no bonus line. The model has to put *something* there. It
cannot write "the document doesn't say," because you didn't give it that option. So it writes `0`.

Now `0` is sitting in your database. It means "the employee earns no bonus." An underwriter reads it
that way. But the truth was "we don't know" — the paystub simply didn't mention bonuses, and this
person might earn $40,000 a year in bonuses.

You did not prevent a gap in your data. **You converted a visible gap into an invisible error.** The
gap was recoverable — someone could have asked for more documents. The error is not, because nothing
about `0` says it was manufactured.

That's the lesson: *required* is not a guarantee that data exists. It is a guarantee that
**something** will be in that slot.

#### In engineering terms

Three schema idioms, three different jobs:

```python
# 1. Nullable union — "the key is present, the value may be unknown"
"bonus_monthly": {"type": ["number", "null"]}

# 2. Enum + "other" + detail — "the value space will grow"
"property_type":        {"type": "string", "enum": [...PROPERTY_TYPES, "other"]},
"property_type_detail": {"type": ["string", "null"],
                         "description": "Free-text when property_type is 'other'."}

# 3. Per-document-type `required` — narrow the contract per context
def _required_sections_for(doc_type: DocumentType) -> list[str]:
    match doc_type:
        case DocumentType.LOAN_APPLICATION:   return ["borrower", "property", "loan"]
        case DocumentType.APPRAISAL:          return ["property"]
        case DocumentType.INCOME_VERIFICATION: return ["borrower", "income"]
```

**Why the enum-plus-`other` pattern rather than a free-text string?** A bare string gives you
`"Single Family"`, `"single-family"`, `"SFR"`, and `"1-unit detached"` for the same concept — you've
moved the normalization problem downstream. A closed enum with no escape forces the model to pick the
*nearest wrong answer* when reality doesn't fit, which is worse than a free-text string because it
looks clean. `enum + "other" + *_detail` gives you clean values for the 95% case and an honest,
inspectable overflow bucket for the rest. The `*_detail` field is also a **product signal**: recurring
values in it tell you which enum member to add next.

**Why per-type `required` rather than one global list?** A paystub has no property. If `property` were
globally required, every paystub extraction would carry a fabricated property object. Narrowing
`required` per document type is how the same canonical schema serves three document shapes without
forcing any of them to lie.

**This exercise's idea, verified against live output.** In
`capstone-submission/02-mortgage-extraction/live-vs-replay.txt`, one of three live calls on a paystub
returned:

```json
"loan":     { "amount": 0 },
"property": { "address": "<UNKNOWN>", "property_type": "other" }
```

There is no loan and no property in an ADP paystub. `"amount": 0` is a fabricated number
indistinguishable downstream from a real $0 loan; `"<UNKNOWN>"` is a placeholder string wearing the
type of an address. **Pydantic accepted both** — they are structurally impeccable. This is the exact
failure the per-type `required` lists exist to prevent, and it demonstrates that schema design is a
*probabilistic* defense: it makes honesty expressible and easy, but it does not make fabrication
impossible.

#### Watch for

- **Nullable ≠ optional.** `required: []` means the key may be absent. `type: ["number","null"]` means
  the key is present with an unknown value. Different statements; pick deliberately.
- **`required` is a contract you are enforcing on the model.** Every entry is a field you are
  guaranteeing will be filled. Only add one you can defend across every document the schema serves.
- **Don't put `required` narrowing in the schema module.** Keep `schema.py` canonical; narrow in
  `tools.py` where document-type context lives.

---

### 3.2 Exercise 2 — Orchestrate two-pass tool choice

**Files:** `mortgage_extractor/pipeline.py`
**Verify:** `pytest tests/test_us02_pipeline.py` (6 tests)

#### In plain English

Why not ask one question — "what kind of document is this, and also extract everything from it"?

Because those are different jobs with different failure modes, and mixing them means a mistake in the
first contaminates the second. If the model half-thinks it's an appraisal and half-thinks it's a
paystub, you get an extraction that's half of each, and no signal that anything went wrong.

Splitting it into two passes gives you a **checkpoint**. After pass one you have a document type, on
its own, with a stated reason. You can log it, count it, alert on unexpected distributions, and stop
early when the answer is "I don't recognize this." Only then do you commit to a type-specific
extraction.

It's the difference between a triage nurse and a doctor. Triage does one cheap, fast, well-defined
job — decide where this goes — and the expensive specialist work happens after, with the routing
already settled.

#### In engineering terms

```python
def run(self, document_text: str) -> MortgageExtraction:
    classification = self.classify_document(document_text)
    if classification.document_type is DocumentType.OTHER:
        raise UnsupportedDocumentTypeError(classification.reason)   # short-circuit
    return self.extract(document_text, classification.document_type)
```

**Pass 1 — forced.** One tool registered, `tool_choice` naming it. The model has no decision to make
except *which* document type:

```python
tool_choice={"type": "tool", "name": "classify_document"}
```

The classifier tool also requires a `reason` string — a one-sentence justification. That field costs
almost nothing and is the difference between a log line that says `type=appraisal` and one you can
debug.

**Pass 2 — `any`, with an escape hatch.**

```python
tools = [doc_type_extractor(doc_type), flag_for_review()]
tool_choice = {"type": "any"}
```

The subtle design point, and the one worth carrying away: **`{"type": "any"}` with one tool is just a
forced call.** It only becomes meaningful when there is a genuine alternative. `flag_for_review` is
that alternative — a way for the model to say "this document is too damaged / off-topic to extract"
without being forced to invent an extraction.

This is the same insight as nullable fields, one level up. *Give the model a legitimate way to
decline, or it will fabricate.* Nullable fields let it decline a **field**; `flag_for_review` lets it
decline a **document**.

**Two short-circuits, not one.** `run()` checks for `OTHER` after classification, and `extract()`
checks again at the top. The second guard exists for callers who skip `run()` — without it they get a
confusing "unexpected tool call" error instead of a proper `UnsupportedDocumentTypeError`. Defensive
guards at public-method boundaries are cheap; confusing errors are expensive.

**Read the tool block, not the text:**

```python
tool_uses = [block for block in response.content if isinstance(block, ToolUseBlock)]
```

#### Watch for

- A response can contain multiple content blocks. `_single_tool_use_block` asserts exactly one
  `tool_use` and raises otherwise — fail loudly on an unexpected shape rather than silently taking
  `[0]`.
- Verify the model called the tool you expected (`block.name != expected_extractor` → raise). With
  `tool_choice="any"` it *could* have called something else.

---

### 3.3 Exercise 3 — Write the extractor system prompt

**Files:** `mortgage_extractor/prompts.py`
**Verify:** `pytest tests/test_us03_prompts.py` (6 tests)

#### In plain English

The schema says what shape the answer takes. The prompt says how to *behave* when reality is messy —
and messy reality is most of the job.

Three behaviors this prompt has to install:

1. **Say nothing rather than guess.** "If the document doesn't state it, return null."
2. **Normalize.** "about 2,400 sq ft" becomes `2400`. "$485,000" becomes `485000.0`. "6.5%" becomes
   `0.065`.
3. **Report contradictions, don't fix them.** If line items don't sum to the stated total, extract
   *both* faithfully. Do not silently correct the document. The mismatch is a finding, and quietly
   repairing it destroys the only evidence that something is wrong.

The third one is the least intuitive and the most important. A helpful assistant "fixes" the typo. A
trustworthy extractor records exactly what the document said and lets a validator downstream decide
what to do about it.

#### In engineering terms

**One source of truth for normalization**, interpolated into every extractor prompt:

```python
NORMALIZATION_RULES = """\
Normalization rules — apply BEFORE writing values into structured fields:
1. Square footage: emit an INTEGER (e.g., "about 2,400 sq ft" → 2400; "~3,100 SF" → 3100).
2. Currency amounts: strip "$" and commas; emit a NUMBER (e.g., "$485,000" → 485000.0).
3. Percentage fields (interest rates, ratios): emit a DECIMAL (e.g., "6.5%" → 0.065).
"""
```

Two prompts (income and appraisal) interpolate the *same constant*. The tests assert this. Duplicated
rules drift, and drifted normalization rules produce fields that are subtly incomparable across
document types.

**The anti-fabrication rule is asserted verbatim** by the test suite:

> `"Return null for any field not explicitly stated in the document. Do not infer, default, or fabricate."`

It is pinned as an exact substring because it is load-bearing. Paraphrasing it is a silent behavior
change, and a test that only checks "some rule about nulls exists" would not catch it.

**Few-shot examples must carry reasoning.** Input/output pairs teach format. `<reasoning>` teaches
*rationale*, which is what generalizes to cases you didn't enumerate:

```xml
<example name="missing-bonus-returns-null">
<reasoning>
The document does not mention bonus, commission, or overtime. Rule #1 says to return null when
the document does not state a value — fabricating zero would imply the employee earned zero
bonus, not that the document is silent about bonus. These are different facts. The downstream
consumer treats null as "we don't know" and zero as "we know it's zero"; conflating them hides
the underlying uncertainty.
</reasoning>
</example>
```

Compare with the `"clean"` example, which reports `commission_monthly: 0.00` — **not null** — because
that document *explicitly stated* `$0.00`. The pair of examples together teach the distinction; either
one alone would be ambiguous. That is what good few-shot design looks like: examples chosen to
**contrast**, not merely to illustrate.

#### Why normalize at extraction time rather than downstream

Four reasons, in rough order of importance:

1. **Context exists here and nowhere else.** Deciding `2,400` means twenty-four hundred rather than
   2.4 requires knowing this is a US appraisal in square feet. The extractor has the whole document;
   a downstream consumer has a lonely string. The same file contains `0.46 acres` and `441 sq ft`.
2. **Once instead of N times.** Every consumer would otherwise write its own parser, and they would
   disagree. The one that mishandles `approximately` becomes a bug nobody can localize.
3. **It's where the type contract is enforced.** `gross_living_area_sqft: int | None` is only
   meaningful if something guarantees an `int` arrives. Deferring normalization defers the type, and
   the schema stops being load-bearing.
4. **Consistency checking depends on it.** The validator subtracts `calculated` from `stated`. It
   cannot subtract `"about 2,400 sq ft"` from anything. **An un-normalized pipeline cannot have a
   consistency validator at all.**

**The honest cost:** normalization is lossy. `approximately` was real information and it is gone —
there is no `is_approximate` flag. For gross living area that's a fine trade. For a field where the
hedge carries legal weight it wouldn't be, and the right design keeps both the normalized value and
the raw span.

---

### 3.4 Exercise 4 — Validate mathematical consistency

**Files:** `mortgage_extractor/models.py` (`Income.calculated_monthly_total`), `validator.py`
**Verify:** `pytest tests/test_us04_validator.py` (8 tests)

#### In plain English

Documents contain the same fact twice: the individual line items, and the total. That redundancy is
free error-checking, and this exercise cashes it in.

Add up the line items yourself. Compare with the printed total. If they differ by more than a
rounding artifact, something is wrong — either the extraction misread a number, or **the document
itself is wrong**. Both are worth a human's attention, and neither is detectable by any amount of
schema strictness.

This is redundancy as a safety mechanism, and it is very old engineering. A checksum works the same
way: send the data, send a summary of the data, and check that they agree.

#### In engineering terms

```python
if extraction.income is not None:
    calculated = extraction.income.calculated_monthly_total
    stated     = extraction.income.stated_monthly_total
    if calculated is not None and stated is not None:      # <-- the guard that matters
        delta = round(calculated - stated, 2)
        if abs(delta) > tolerance:
            discrepancies.append(Discrepancy(field="total_monthly_income",
                                             calculated=round(calculated, 2),
                                             stated=round(stated, 2),
                                             delta=delta))
```

**Design decision 1 — `None`, not `0.0`.**

```python
@property
def calculated_monthly_total(self) -> float | None:
    components = [self.base_monthly, self.bonus_monthly, self.commission_monthly,
                  self.overtime_monthly, self.other_monthly]
    non_null = [c for c in components if c is not None]
    return sum(non_null) if non_null else None      # None, never 0.0
```

Returning `0.0` would make an income-less appraisal compare `0.0 == 0.0` and report `consistent:
true` — technically the same verdict, arrived at by *actively checking a vacuous comparison* rather
than correctly declining to check. A document where extraction silently failed would be
indistinguishable from one that legitimately has no income.

Verified empirically in `capstone-submission/perturbations/system2/null-vs-zero-probe.txt`. Note this
is the **same absent-vs-zero distinction as Exercise 1's nullable schema**, one layer up. The
principle recurs: *make "nothing here" a distinct, first-class value at every layer.*

**Design decision 2 — same-unit invariant.** Only the five `*_monthly` fields enter the sum.
`bonus_ytd` is year-to-date; adding it to monthly figures produces a number in no coherent unit that
would surface discrepancies that don't exist. The explicit five-element list *is* the invariant —
an `Income` model that iterated all numeric fields would silently break the moment someone added
`base_annual`.

**Design decision 3 — a non-zero default tolerance.** `DEFAULT_TOLERANCE_USD = 1.00` absorbs
cent-level OCR rounding. Zero tolerance produces false positives on every rounding artifact, and a
validator that cries wolf gets ignored. Tolerance is a per-call override for domains that demand it.

#### What probing the boundary revealed

`capstone-submission/perturbations/system2/tolerance-boundary-probe.txt` swept delta across the
threshold:

```
 target delta       stated   |delta|  consistent?
        1.000     9641.170     1.000         True     <- expected: comparison is > , not >=
        1.001     9641.169     1.001         True     <- NOT expected
        1.010     9641.160     1.010        False
```

A delta of $1.001 is **not** flagged. Two lines act in sequence:

```python
delta = round(calculated - stated, 2)   # rounds FIRST
if abs(delta) > tolerance:              # compares SECOND
```

`1.001` rounds to `1.00`, and `1.00 > 1.00` is `False`. The **effective** threshold is $1.005, not the
documented $1.00.

Harmless at this magnitude — but it is a real gap between a named constant and runtime behavior, and
it is invisible from reading either line alone. **Thresholds are the least-exercised part of a
validation system and the least visible in normal output, which is exactly why they're worth probing
deliberately.**

#### Watch for

- `consistent: true` has two meanings: "we checked and they agree" and "there was nothing to check."
  A `ValidationReport` for a production system should probably distinguish `CONSISTENT`,
  `INCONSISTENT`, and `NOT_APPLICABLE`.
- The exit code is part of the interface: `0` consistent, `1` discrepancy, `3` unsupported type,
  `4` flagged for review. That's what makes the CLI composable in a shell pipeline.

---

## 4. Project 2 — Insurance policy pipeline

**Scenario.** Insurance policy renewals arrive in batches. Each must be extracted, checked, and either
auto-approved or sent to a human. The volume makes reviewing everything impossible; the stakes make
reviewing nothing unacceptable.

**Arc.** Retry → batch → review → route. Where Project 1 asked *is this output well-formed and
coherent?*, Project 2 asks *what do we do about it, at volume, when we can't check everything?*

```
                        ┌──────────────────────────────────────────┐
  document ──> extract_with_retry ──> PolicyExtraction ────────────┤
                        │  (US-01)         │                       │
                        │                  ├─> independent_review ─┤  (US-03, different model,
                        │                  │      ReviewResult     │   no extractor context)
                        │                  │                       │
                        │                  └─> integration_pass ───┤  (US-03, pure function)
                        │                        [IntegrationFinding]
                        │                                          │
                        └─> RetryFutileEscalation                  ▼
                              (missing_source, 1 call)     route_extraction  (US-04)
                                                                   │
                                       ┌───────────────────────────┴──────────┐
                                       ▼                                      ▼
                                 auto_approve                           human_review
                                       │
                            apply_stratified_spot_check
                                       ▼
                                  spot_check
```

### 4.1 Exercise 1 — Retry with error feedback

**Files:** `extractor.py` (message building), `validator.py`, `retry.py`
**Verify:** `pytest tests/test_us01_retry.py` (13 passed, 1 live-skipped)

#### In plain English

When an answer comes back wrong, you have three options: give up, try again, or try again *with
information about what went wrong*. The third is dramatically better than the second — but only for
certain kinds of wrong.

The insight that makes this exercise worth its weight: **classify the failure before you react to
it.**

- The model returned a *negative* premium. That's a misreading. Show it the error; it can fix it.
- The line items don't sum to the total. Also potentially a misreading. Worth one more look.
- The field is null because **the document genuinely doesn't contain it**. Nothing to fix. The
  information is not there. Retrying cannot help.

And that third case isn't just wasteful — it's *dangerous*. The retry message says "this came back
null, try again." A model that complies on attempt two has to produce a number that is not in the
document. **A retry loop pointed at a missing-information failure is a machine for pressuring the
model into fabrication.** You'd convert a detectable gap into an undetectable error, and the
fabricated value would arrive with the same shape, the same type, and often the same confidence as a
real one.

#### In engineering terms

The validator's job is not merely to detect but to **classify**:

```python
Category = Literal["format", "missing_source", "consistency"]

@dataclass(frozen=True)
class ValidationError:
    field: str
    observed_value: str
    category: Category           # <-- drives the retry decision
    detected_pattern: str        # <-- drives run-level aggregation
    message: str                 # <-- goes back to the model verbatim
```

Checks run in a deliberate order — absence first, because an absent field can't be range-checked:

```python
def validate_extraction(extraction):
    err = _check_required_present(extraction)              # -> missing_source
    if err is not None: return err
    err = _check_numeric_ranges(extraction)                # -> format
    if err is not None: return err
    return _check_premium_components_consistency(extraction)  # -> consistency
```

The loop branches on category:

```python
for attempt_index in range(max_retries + 1):
    ...
    error = validate_extraction(extraction)
    if error is None:
        return build_extraction(...)                 # success

    if error.category == "missing_source":
        return RetryFutileEscalation(...)            # STOP. Zero further API calls.

    prior_attempts.append({...})                     # feed the error back and retry
```

**Feedback must be verbatim.** The prior extraction *and* the validator's message go into the next
request:

```
<prior_attempt index="1">
  <extraction>{'premium_amount': -1847.62, ...}</extraction>
  <validation_error field="premium_amount" category="format" detected_pattern="negative_premium">
    premium_amount is -1847.62, which is negative. Premium amounts must be a positive number
    in USD. Re-read the document and extract the correct positive value.
  </validation_error>
</prior_attempt>
```

"Your answer was invalid" gives the model nothing. The offending value plus a specific correction
gives it something to act on.

**Escalation is a return type, not an exception:**

```python
ExtractionOutcome = PolicyExtraction | RetryFutileEscalation
```

A union forces every caller to handle both branches at the type level; `mypy --strict` enforces it.
An exception lets callers ignore the case until production.

**`detected_pattern` is the observability hook.** It's a stable tag (`negative_premium`,
`endorsements_absent`, `premium_does_not_match_components`) that `summary.py` aggregates across a run:

```json
"pattern_summary": {
  "endorsements_absent": {"count": 1, "policies": ["POL-2025-009"], "categories": ["missing_source"]},
  "premium_does_not_match_components": {"count": 1, "policies": ["POL-2025-010"],
                                        "categories": ["consistency"]}
}
```

That's the difference between "5 failures today" and "5 failures, all `negative_premium`, all from one
carrier's OCR pipeline." The first is a number; the second is a fix. **This is the single cheapest
observability feature in the whole repo** — one string field on an error type — and it converts a
failure count into a diagnosis.

**Retries-exhausted also escalates**, tagged `retries_exhausted__<original_pattern>` so it stays
distinguishable from a first-attempt `missing_source`.

#### Verified

`capstone-submission/perturbations/system1/`: blanking the premium in a copied document produced
`missing_source` / `premium_amount_absent` and **exactly one** `HTTP Request` line despite
`--max-retries 3`. The unit test pins the same invariant at `tests/test_us01_retry.py:360`:
`assert client.call_count == 1`.

The contrast that makes it meaningful: the *unperturbed* document also makes one call. What changed
is not the effort spent but the **terminal state** — and a `consistency` failure genuinely does
retry, visible as two `validation_failed` lines before success for POL-2025-010 in
`01-policy-pipeline/pipeline-run.txt`.

---

### 4.2 Exercise 2 — Batch processing and SLA

**Files:** `policy_extractor/batch.py`
**Verify:** `pytest tests/test_us02_batch.py` (12 tests)

#### In plain English

Processing documents one at a time as they arrive is the most expensive way to do it. The Batches API
costs about half as much, at the price of latency — you submit a pile, wait, and collect.

That trade creates a scheduling question. If you promise results within 24 hours and a batch takes 6
hours to complete, how often must you submit? Not once a day — a document arriving just after the
daily submission would wait ~24 hours in the queue *plus* 6 hours processing, blowing the SLA. You
need the queue wait plus the processing time to fit inside the promise.

And there's a second question, about risk. Submitting 10,000 documents in one batch means that if your
prompt has a bug, you discover it 6 hours and 10,000 documents later. So you run a handful in
real-time first, check the success rate, and only authorize the batch if the sample looks healthy.
A canary.

#### In engineering terms

**The SLA math:**

```python
def submission_frequency(sla_hours: float, batch_eta_hours: float) -> int:
    if sla_hours < batch_eta_hours:
        raise SLATooTightError(...)          # physically impossible; fail loudly
    head_room = sla_hours - batch_eta_hours  # time available for queue wait
    return max(1, ceil(24 / (head_room + batch_eta_hours)))
```

The `SLATooTightError` is the interesting part. When the SLA is shorter than the batch's own
completion time, no submission frequency works — the correct response is an explicit error naming the
impossibility, not a silently clamped value that quietly misses the target forever. **Encode
impossible configurations as errors, not as defaults.**

**The dry-run gate:**

```python
sample = dry_run_sample(extractor_client=..., policies=..., sample_size=3)
if not args.force and sample.first_pass_success_rate < args.sample_threshold:
    print(f"Sample first-pass success rate {sample.first_pass_success_rate:.0%} below "
          f"threshold {args.sample_threshold:.0%}; aborting. Use --force to override.")
    return 3
```

Note `--force`. A gate with no override becomes an obstacle people route around; a gate with an
explicit, logged override stays a gate. And it reports `pattern_summary`, so an abort tells you
*which* pattern is failing, not just that the rate is low.

**Two-round resubmission**, with per-item outcomes correlated by `custom_id`:

| Round-1 outcome | Round-2 treatment |
|---|---|
| success + clean | final, no resubmission |
| success + `missing_source` | escalate immediately — never resubmitted |
| success + `format`/`consistency` | resubmit **with** `prior_attempts` feedback |
| errored / expired / canceled | resubmit **without** feedback (nothing to feed back) |

The `missing_source` row is Exercise 1's rule surviving the move to batch. The futile/recoverable
distinction is a property of the *failure*, not of the transport, so it must hold in both paths — and
the last row shows the mirror case: an infrastructure error carries no model output, so there is no
feedback to thread in. Retry, but blindly.

Any second-round failure is terminal. Two rounds, not N, because an unbounded retry loop over a batch
API is an unbounded bill.

#### Watch for

- `custom_id` correlation is load-bearing. Batch results come back unordered; without a stable id per
  item you cannot match results to inputs.
- The dry-run sample uses the *real-time* API, deliberately. Its purpose is fast feedback, which the
  batch path cannot give.

---

### 4.3 Exercise 3 — Independent review and the integration pass

**Files:** `policy_extractor/reviewer.py`
**Verify:** `pytest tests/test_us03_review.py` (13 tests)

#### In plain English

Two second-opinion mechanisms, deliberately different in kind.

**The independent reviewer** is a second model that looks at the original document and the proposed
extraction, and says field by field whether it agrees. The word doing all the work is *independent*.
It sees the document and the answer — and nothing else. Not the first model's prompt, not its
reasoning, not its tool-call history.

Why does that matter so much? Because a reviewer who sees the original reasoning tends to be
persuaded by it. If the first model explains "the premium is $1,847.62 because the Premium Summary
line says so," a reviewer reading that explanation is anchored — it's now checking whether the
reasoning is *coherent*, not whether the answer is *right*. Coherent wrong answers are exactly the
failure mode you're trying to catch. Independence is not a nicety; it's the entire mechanism.

It's the same reason double-entry bookkeeping uses two people, and why peer review is blind.

**The integration pass** is different: no model at all. Pure Python checks for internal
contradictions within one record. If the coverage limit is $100,000 but the endorsements promise
$750,000, no reading of any single field is wrong — the *combination* is impossible. A per-field
reviewer, checking fields one at a time, structurally cannot see this.

#### In engineering terms

**Independence enforced by construction**, not by instruction:

```python
def build_review_messages(*, source_document: str, extracted_record: dict) -> tuple[list, str]:
    """Critically: nothing from the extractor's prompts, reasoning, or tool-call history
    flows into this prompt. Only the raw source document + the proposed extraction."""
```

The function *signature* is the guarantee — it accepts only two things, so it cannot leak extractor
context even by accident. That's stronger than a prompt saying "ignore the previous reasoning," and
it's testable: `test_ac_03_04_reviewer_prompt_has_no_extractor_artefacts`.

**A different model, deliberately:**

```python
DEFAULT_EXTRACTOR_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_REVIEWER_MODEL  = "claude-sonnet-4-6"
```

Two reasons. Economically, extraction is high-volume and review is a check — spend the capable model
where judgment is needed. Statistically, **two instances of the same model share failure modes**. If
Haiku systematically misreads a particular layout, a second Haiku call is likely to misread it the
same way, and your "independent" check silently agrees with the error. Different models decorrelate
errors. (This is the same reason you don't test a system with the code that generated it.)

**The integration checks** are pure functions over one extraction:

```python
def integration_pass(extraction: PolicyExtraction) -> list[IntegrationFinding]:
    findings = [_check_coverage_limit_vs_endorsements(extraction),
                _check_endorsements_vs_exclusions(extraction)]
    components_check = _check_premium_vs_components(extraction)
    if components_check is not None:
        findings.append(components_check)
    return findings
```

1. **`coverage_limit >= sum(endorsement.limit)`** — arithmetic impossibility.
2. **Endorsement/exclusion contradiction** — fuzzy bigram overlap on content words. If an endorsement
   grants "Rideshare Coverage" while an exclusion removes "ride-share use," the policy contradicts
   itself. This one is *heuristic* and will produce false positives; that's acceptable because its
   output routes to a human, not to a rejection.
3. **Premium vs. components** — same arithmetic as the validator, reused rather than reimplemented.

Note that **each check returns a `pass` finding rather than silence** when it's skipped:

```python
IntegrationFinding(check_name="coverage_limit_exceeds_endorsement_sum", status="pass",
                   details="coverage_limit or endorsements absent — check skipped.")
```

"We checked and it's fine" and "we couldn't check" are different states, and both are recorded with
a reason. Silence would conflate them — the same absent-vs-zero principle again, now applied to
*checks* rather than *values*.

#### Verified

The reviewer signal turned out to be doing nearly all the work
(`capstone-submission/perturbations/system1/D-signal-dominance.txt`): 8 of 9 records, versus 1 for
confidence and 0 for integration. Removing it drops human review from 8 to 1.

That is the empirical case for independent review — and simultaneously a caution. A signal firing on
89% of records is either finding real problems or is miscalibrated, and *the counts alone cannot tell
you which*. Answering it requires ground truth: sample the disagreements, have a human adjudicate,
and feed the result into the calibration report. Which is precisely what Exercise 4 builds.

---

### 4.4 Exercise 4 — Deterministic HITL routing, stratified sampling, calibration

**Files:** `policy_extractor/routing.py`
**Verify:** `pytest tests/` (45 passed, 3 live-skipped)

#### In plain English

Now you have three opinions about each record: the model's own confidence, an independent reviewer's
field-by-field verdict, and a set of internal-consistency checks. This exercise turns them into a
decision — and the decision must be made by **rules you can read**, not by a model.

Why rules? Because "why was this policy auto-approved?" is a question with legal weight in insurance.
"The model felt good about it" is not an answer. "All six confidences were at or above 0.90, the
independent reviewer agreed on every field, and all three integration checks passed" is an answer —
one you can print, audit, and argue with.

Two more pieces:

**Spot-checking.** Auto-approved records are never seen by anyone, which means if the model starts
drifting you'd never find out. So a small random sample gets reviewed anyway. Stratified by policy
type, so the rare types stay covered.

**Calibration.** Track, over time, whether stated confidence matches observed accuracy — sliced, so a
single broken category can't hide inside a healthy average.

#### In engineering terms

**Routing is a pure function:**

```python
def route_extraction(*, extraction, review, integration_findings,
                     threshold=DEFAULT_CONFIDENCE_THRESHOLD) -> RoutingDecision:
    fields_below  = sorted(f for f, c in extraction.confidence.items() if c < threshold)
    disagreements = sorted(f for f, a in review.agreements.items() if a.agreement == "disagree")
    integration_failures = sorted(f.check_name for f in integration_findings if f.status == "fail")

    if fields_below or disagreements or integration_failures:
        decision = "human_review"
    else:
        decision = "auto_approve"
```

**The combination rule is OR, not AND.** Any one signal diverts to human review; `auto_approve`
requires all three clear simultaneously. The full truth table is in
`capstone-submission/perturbations/system1/C-routing-truth-table.txt` — all 8 combinations, generated
by calling the real function with constructed inputs and no API:

```
conf<thr  reviewer  integr  -> DECISION       reason
False     False     False   -> auto_approve   all confidence at/above threshold, reviewer agrees, integration clean
False     False     True    -> human_review   integration_failure=[...]
False     True      False   -> human_review   reviewer_disagreement=['coverage_limit']
True      False     False   -> human_review   fields_below_threshold=['coverage_limit']
... (all remaining combinations -> human_review)
```

(The docstring phrase "(confidence ∧ reviewer ∧ integration)" describes what must hold to
**auto-approve** — the conjunction is on the *clean* side.)

**Every decision carries its reason:**

```json
{ "policy_id": "POL-2025-002",
  "decision": "human_review",
  "reason": "reviewer_disagreement=['coverage_limit', 'deductible', 'endorsements']",
  "fields_below_threshold": [],
  "reviewer_disagreements": ["coverage_limit", "deductible", "endorsements"],
  "integration_failures": [],
  "confidence_summary": {"coverage_limit": 0.95, "deductible": 0.95, ...} }
```

Note it records **all three signal arrays**, not just the ones that fired, plus the full confidence
map. That's what makes the counterfactual analysis in `D-signal-dominance.txt` possible after the
fact. *Log the inputs, not just the output* — you cannot reconstruct what you did not record, and
with a nondeterministic upstream you cannot re-derive it either.

**Stratified spot-check:**

```python
for indices in by_type.values():           # bucketed by policy_type
    n = len(indices)
    k = min(max(1, math.ceil(sample_pct * n)), n)   # <-- max(1, ...) is the whole point
    promoted_indices.update(rng.sample(indices, k))
```

`max(1, ceil(...))` guarantees every stratum with at least one eligible record contributes at least
one sample. Only `auto_approve` records are eligible — `human_review` records are already going to a
person, so sampling them would be redundant.

**Calibration, sliced:**

```python
buckets[(label.policy_type, label.field)].append(label)
brier = sum((b.predicted_confidence - (1.0 if b.correct else 0.0)) ** 2 for b in bucket) / n
```

#### The determinism subtlety worth internalizing

The routing layer is deterministic. The sampler is stochastic but seeded, and therefore reproducible.
Neither of those makes the *pipeline* reproducible, because both sit on top of live model calls.

`capstone-submission/01-policy-pipeline/seed-determinism.txt` records two runs of the identical
command with identical `--seed 42`:

```
POL-2025-007   run1: spot_check      run2: human_review    <-- DIFFERS
               run1 reviewer disagreements: []
               run2 reviewer disagreements: ['deductible']
```

The seed didn't change. The router didn't change. The **reviewer's judgment** changed. A separate
controlled probe with the model held out (`sampler-seed-probe.txt`) confirms the sampler itself is
exactly reproducible: seed 42 twice gives identical selections, seed 7 gives different ones.

**The operational conclusion:** a deterministic system built on a nondeterministic input is only as
reproducible as its inputs. This is *why* `reason` and the signal arrays must be recorded at decision
time rather than recomputed during an audit — recomputing would produce a different answer than the
one the decision was actually made on.

---

## 5. Project 3 — Supply-chain multi-source synthesis

**Scenario.** Is Meridian Components a supply-chain risk? Four sources disagree: the supplier's own
audit (JSON), your logistics data (CSV), your internal quality database (SQLite), and trade-press
articles (prose). They use different formats, different vocabularies, and different dates, and one of
them is about a *different company with the same name*.

**Arc.** One claim shape → shared memory + synthesis → resilience. Where Projects 1 and 2 handled one
document at a time, this one has to reconcile many sources that don't agree — and stay honest about it.

```
  audit.json ──> read_audit ──────┐
  logistics.csv ─> read_logistics ┤
  quality.sqlite > read_quality ──┼──> [ReaderResult]  ──> ok? ──> [Claim] ──> SharedMemory
  news/*.txt ───> read_news ──────┘         │                                   (Chroma, 384-dim
                  (LLM extraction)          │                                    MiniLM embeddings)
                                            │                                        │
                                     not ok │                                        ▼
                                            ▼                                  group_by_metric
                                     FailureContext                                  │
                                     {failure_type, attempted,                       ▼
                                      partial_results, alternatives}             _classify
                                            │                                        │
                                            └────> gap annotation ──> build_briefing ┘
                                                                            │
                        ┌───────────────────────────────────────────────────┤
                        ▼                     ▼                             ▼
                Well-Established          Contested                    Incomplete
             (1 source, or 2+ agreeing)  (2+ disagreeing,          (tracked metric with
                                          both values kept)         no usable source)
```

### 5.1 Exercise 1 — One `Claim` shape for every source

**Files:** `models.py`, `readers.py`, `news_extraction.py`
**Verify:** `pytest tests/test_readers.py`

#### In plain English

Four sources, four formats. You could write four downstream handlers — but then every later step has
to know about all four, and adding a fifth source means touching everything.

Instead: **make every source produce the same shape**. A `Claim` — one statement about the supplier,
carrying where it came from, when, and how confident the reader is. After the readers, nothing
downstream knows or cares whether a fact came from a spreadsheet or a newspaper.

The critical design choice is what rides *along with* each claim. Not just "on-time delivery is 95%"
but "**the supplier's audit, dated 2026-04-10**, says on-time delivery is 95%." The provenance is not
metadata for display — it's what makes conflict detection and staleness detection possible at all.

The second design choice is that a reader **cannot crash the run**. It returns a result object that
is either fine or carries a structured description of what went wrong.

#### In engineering terms

```python
class Claim(BaseModel):
    model_config = ConfigDict(frozen=True)     # provenance can't be mutated downstream
    claim: str          # human-readable statement
    evidence: str       # what supports it
    source: str         # supplier_audit | logistics | internal_quality | industry_news
    source_date: date   # when this was true
    confidence: float = Field(ge=0.0, le=1.0)
    metric_id: str      # groups claims about the same quantity — the join key
    value: float | None = None   # numeric metrics only; qualitative findings leave it None
    unit: str | None = None
    needs_identifier: bool = False       # ambiguous entity — reader refused to guess
    candidates: tuple[str, ...] = ()     # ...and named the possibilities
```

`metric_id` is the join key. `on_time_delivery_rate` from the audit and from logistics group together
*because they share that string*, which is what makes them comparable and therefore conflict-checkable.

**Errors as values:**

```python
class ReaderResult(BaseModel):
    source: str
    ok: bool
    claims: list[Claim] = Field(default_factory=list)   # possibly empty — a VALID empty result
    error: FailureContext | None = None

class FailureContext(BaseModel):
    failure_type: str          # "timeout" | "file_not_found" | ...
    attempted: str             # what we tried, for the log
    partial_results: list[Claim] = Field(default_factory=list)   # what we got before dying
    alternatives: list[str] = Field(default_factory=list)        # what a human could do instead
```

`FailureContext.alternatives` is unusual and worth stealing. The failure carries **suggested
remediation** — `["retry the 3PL extract", "proceed with available sources and annotate the gap"]`.
The code that knows how a thing broke is the code best positioned to say what to try next, and that
knowledge is usually lost by the time an exception reaches a handler.

Note also that `ok=True` with `claims=[]` is explicitly valid: "I read the source successfully and it
had nothing to say" is a different state from "I couldn't read the source." Pinned by
`test_empty_result_is_ok_not_error`. The absent-vs-zero principle, a third time.

**Three deterministic readers, one LLM reader.** `read_audit`, `read_logistics` and `read_quality`
parse JSON, CSV and SQLite — no model involved. Only `read_news` calls Claude, because prose is the
one source that cannot be parsed.

This is the architectural decision that makes the whole system trustworthy, and it is visible in the
runs: `capstone-submission/03-supply-chain/live-vs-offline-briefing.txt` shows the live news reader
producing **18 metrics against the recorded run's 9**, with different claim text and different
`metric_id` naming for the same articles. Meanwhile the Contested section — the headline finding — is
**byte-identical**, because both of its values come from deterministic readers.

> **The load-bearing, conflict-detecting work runs on parsers. The LLM is confined to the one source
> that has no parser, where instability is survivable.**

That is a reusable architectural rule, not a fact about this repo.

**The ambiguity escape hatch.** `data/meridian/news/ambiguous_meridian.txt` describes financial
distress at "Meridian" — which could be Meridian Components (the parts supplier) or Meridian Logistics
Group (a freight forwarder). The prompt instructs:

> "If the article names the supplier ambiguously — multiple distinct entities could be the subject —
> do NOT guess which one: emit the claim with `needs_identifier=true` and list the candidate entity
> names, so a human can supply an identifier."

The claim is kept, flagged, and escalated — not dropped, not resolved by guessing. Same pattern as
`flag_for_review` and nullable fields: **a structured way to say "I don't know" beats a forced guess.**

---

### 5.2 Exercise 2 — Shared memory and the synthesis briefing

**Files:** `memory.py`, `synthesis.py`
**Verify:** `pytest tests/test_memory.py tests/test_synthesis.py`

#### In plain English

**Shared memory** is a searchable pool of every claim, where search works by *meaning* rather than by
exact words. Ask it "delivery delays" and it surfaces claims about port strikes and late shipments
even though those words don't appear in your query. It exists so the system can notice that two
sources are talking about the same thing when they used different labels.

**Synthesis** sorts every metric into one of three buckets:

- **Well-Established** — one source says it, or several agree.
- **Contested** — two or more sources materially disagree. **Both values are printed, with sources
  and dates. Nothing is averaged.**
- **Incomplete** — a metric we track that no usable source reported.

The hardest discipline is the Contested bucket. Every instinct in software says "resolve the
ambiguity, return one number." Here that instinct is wrong. Averaging 95% and 78% gives 86.5% — a
figure no source reported, describing no state of the world, that destroys the only genuinely
interesting fact: **the supplier's self-report doesn't match our measurements.**

#### In engineering terms

**Memory** is Chroma with a local sentence-transformers model (`all-MiniLM-L6-v2`, 384 dims) — no API
key, fully offline:

```python
def add_claims(self, claims: list[Claim]) -> None:
    for c in claims:
        ids.append(_claim_id(c))
        docs.append(f"{c.claim} {c.evidence}")     # what gets embedded
        metas.append({"source": c.source, "metric_id": c.metric_id,
                      "source_date": c.source_date.isoformat(),
                      "confidence": c.confidence,
                      "claim_json": c.model_dump_json()})   # <-- full round-trip
```

Serializing the whole `Claim` into `claim_json` means retrieval reconstructs the complete object —
`Claim.model_validate_json(m["claim_json"])` — so **provenance survives the vector-store round trip**.
A naive implementation storing only the embedding and the text would silently drop source and date at
exactly the step where they matter most.

**Grouping** is union-find over claims, with two merge rules:

```python
# 1. identical metric_id  -> always the same group
# 2. semantic near-duplicates: memory says they're neighbours
#    AND their metric_ids share >= 2 tokens (e.g. defect_rate / defect_rate_ppm)
if len(_tokens(r.metric_id) & _tokens(c.metric_id)) >= 2:
    union(i, jdx)
```

Two independent conditions must both hold — embedding neighbourhood *and* lexical overlap. Embeddings
alone over-merge (`defect_rate_ppm` and `field_return_rate` are semantically close but different
quantities); token overlap alone misses genuine synonyms. Requiring both is a cheap precision/recall
compromise, and the kind of guardrail worth adding whenever an embedding similarity drives a
*structural* decision.

**Classification:**

```python
REL_TOL = 0.10   # values within 10% are treated as agreeing

def _disagree(values: list[float]) -> bool:
    lo, hi = min(values), max(values)
    denom = max(abs(lo), abs(hi), 1e-9)
    return (hi - lo) / denom > REL_TOL

def _classify(group) -> tuple[str, str]:
    n_sources = len({c.source for c in group.claims})
    values = _source_values(group.claims)
    if len(values) >= 2 and _disagree(list(values.values())):
        return CONTESTED, f"{n_sources} sources, conflicting"
    if n_sources >= 2:
        return WELL_ESTABLISHED, f"corroborated across {n_sources} sources"
    return WELL_ESTABLISHED, "single source only"
```

**Escalation is explicit, never sentiment-driven:**

```python
if any(c.needs_identifier for c in claims):
    return True, "ambiguous supplier identity — request an identifier"
if metric_id in HIGH_IMPACT and classification == CONTESTED:
    return True, "high-impact metric is contested across sources"
if metric_id in HIGH_IMPACT and classification == INCOMPLETE:
    return True, "high-impact metric has no usable source"
```

Note the docstring: *"Explicit escalation criteria — never confidence/sentiment."* Escalation keys on
`metric_id ∈ HIGH_IMPACT` and the structural classification. It never asks a model whether something
sounds alarming. Same lesson as Project 2's router: **the decision layer is rules over signals, not
vibes.**

**Synthesis is deterministic Python, not an LLM call** — which is what lets the module docstring
promise that provenance preservation and conflict annotation are *guaranteed, not merely prompted*.
A synthesis step implemented as "here are 20 claims, write me a briefing" would preserve provenance
only as reliably as the model felt like it that day.

#### What probing the threshold revealed

`capstone-submission/perturbations/system3/conflict-threshold-sweep.txt` rewrote the audit's
`on_time_delivery_rate` across nine values while logistics stayed pinned at 78%:

```
audit     logistics rel.diff    SECTION            badge
86        78        0.0930      Well-Established   corroborated across 2 sources
86.6      78        0.0993      Well-Established   corroborated across 2 sources
86.7      78        0.1003      Contested          2 sources, conflicting  ESCALATE
95        78        0.1789      Contested          2 sources, conflicting  ESCALATE
```

The boundary sits at 86.67, exactly as the formula predicts. Two consequences that the unperturbed
run cannot show you:

1. **The tolerance is relative to the larger value, so the band is asymmetric.** An 8.6-point gap
   between 78 and 86.6 is "corroborated"; the same 8.6-point gap between 86.4 and 95 is "contested."
2. **A single relative tolerance is doing two different jobs** — absorbing measurement noise, and
   defining business-relevant disagreement. 10% is a reasonable answer to the first and a poor one to
   the second for a service-level metric. A supplier reporting 86% against our measured 78% is filed
   under the *same badge* as genuine agreement, with the spread neither shown nor escalated.

The fix is per-metric tolerances (on-time delivery might warrant 2%, defect-rate ppm 20%) plus
rendering the spread even when a metric is classified as corroborated, so "close enough" stays visible.

---

### 5.3 Exercise 3 — The resilient coordinator

**Files:** `readers.py` (timeout path), `coordinator.py`
**Verify:** `pytest tests/` (34 tests)

#### In plain English

Sources fail. The 3PL portal times out, the database is locked, an API is down. The question is what
your investigation does about it.

Aborting is the wrong answer: three of four sources succeeded, and their findings have nothing to do
with a logistics outage. Throwing them away turns a partial answer into no answer.

Silently continuing is also wrong: a reader who isn't told the logistics source is missing will assume
the briefing is complete.

The right answer is **finish, and say what's missing** — and crucially, distinguish *"we couldn't
ask"* from *"we asked and nobody knew."* Those are different problems with different fixes. The first
is retryable and the data probably still exists. The second is a coverage gap that no retry fixes.

#### In engineering terms

**The timeout path returns rather than raises**, and keeps what it had:

```python
if fail_after is not None and fail_after < len(rows):
    partial = _logistics_claims(rows[:fail_after]) if fail_after > 0 else []
    return ReaderResult(source=LOGISTICS, ok=False,
        error=FailureContext(failure_type="timeout",
                             attempted=f"read {len(rows)} shipment rows from {path}",
                             partial_results=partial,
                             alternatives=["retry the 3PL extract",
                                           "proceed with available sources and annotate the gap"]))
```

**The coordinator recovers locally and attributes gaps:**

```python
ok_claims = [c for r in results if r.ok for c in r.claims]
present = {c.metric_id for c in ok_claims}

for r in results:
    if r.ok or r.error is None: continue
    unavailable_sources.append(f"{r.source} unavailable ({r.error.failure_type})")
    for metric_id in EXCLUSIVE_METRICS.get(r.source, ()):
        if metric_id not in present:
            unavailable[metric_id] = f"{r.error.failure_type} reading {r.source}"

mem.add_claims(ok_claims)     # only successful claims are vectorized
```

Two details worth noting. **Only successful claims are vectorized** — `partial_results` from a failed
reader are preserved in the `FailureContext` for diagnostics but never enter shared memory, because
partial data would be indistinguishable from complete data once embedded. And gap attribution is
driven by an explicit table:

```python
LOGISTICS_EXCLUSIVE_METRICS = ("late_shipment_count",)
EXCLUSIVE_METRICS = {"logistics": LOGISTICS_EXCLUSIVE_METRICS}
```

Only metrics this source is the *sole* provider of get reported as gaps. Metrics another source also
covers aren't gaps — they're just less corroborated.

#### The finding that matters most

`capstone-submission/03-supply-chain/timeout-diff.txt`. Four behaviors work exactly as designed:

1. **The run finishes** — exit 0, complete briefing.
2. **The outage is stated, not inferred** — `> Sources unavailable: logistics unavailable (timeout)`.
3. **"Unreachable" ≠ "nothing to report"** — two adjacent Incomplete entries carry different causes:
   `_[missing source: timeout reading logistics]_` vs
   `_[missing source: no source reported this metric]_`.
4. **Corroboration is lost, not faked** — `average_lead_time_days` keeps its 12.0-day value but is
   demoted from `[corroborated across 2 sources]` to `[single source only]`. The number didn't change;
   the confidence in it did, and the briefing says so.

And then the fifth thing, which is not by design:

```
normal:   ## Contested        ### on_time_delivery_rate _[2 sources, conflicting]_ ⚠️ ESCALATE
                                  95.0% — supplier_audit (2026-04-10)
                                  78.0% — logistics     (2026-04-05)

timeout:  ## Well-Established ### on_time_delivery_rate _[single source only]_
                                  95.0% — supplier_audit (2026-04-10)
          ## Contested        _none_
```

**The contested metric was promoted to Well-Established.** The disagreement wasn't resolved — the
dissenting source went offline. The surviving value is the supplier's own self-reported 95%, the
optimistic one; the pessimistic 78% was ours. The Contested section now reads `_none_` and the
⚠️ ESCALATE flag is gone.

The mechanism is exactly the `EXCLUSIVE_METRICS` table above: `on_time_delivery_rate` is *not* in
`LOGISTICS_EXCLUSIVE_METRICS`, because the audit also reports it. So no gap is recorded — the metric
simply becomes single-source, and single-source means Well-Established.

> **Graceful degradation is not neutral. Losing a source doesn't merely reduce coverage — it can
> convert a known disagreement into false confidence, and here it does so in the reassuring
> direction.**

The `_[single source only]_` badge and the header banner are the only things standing between this
briefing and a reader who concludes on-time delivery is fine.

**Operational conclusions:**
- Source availability is a **data-quality** metric, not an infrastructure one. It belongs on the same
  dashboard as the findings.
- A metric that was Contested last run and is Well-Established this run **because a source dropped
  out** deserves its own alert. Classification changes driven by coverage changes are a distinct
  event class from classification changes driven by new evidence.
- A better design would keep `on_time_delivery_rate` in Contested with the surviving value plus an
  explicit `[conflicting source unavailable]` annotation — degrading the *confidence* without
  discarding the *memory of the conflict*.

#### The other honest finding: a required date manufactures dates

`capstone-submission/03-supply-chain/live-vs-offline-briefing.txt`. Three live claims came back dated
`2024-01-01`, all from `ambiguous_meridian.txt` — an article that contains **no date at all**. The
recorded fixture dated the same article `2026-03-09`. Two runs, two different invented dates.

The cause is a schema decision:

```python
class Claim(BaseModel):
    source_date: date        # NOT `date | None`
```
```python
"required": ["claim", "evidence", "source_date", "confidence", "metric_id", ...]
```

The schema demands a date, the prompt assumes one exists ("Each claim carries the article's
publication date as `source_date`"), and null is not expressible — so the model invents.

**This is Project 1's Exercise 1 lesson, violated by Project 3.** `Income.bonus_monthly` is
`float | None`, the document is silent, the model returns null, and the pipeline records an honest
absence. `Claim.source_date` is `date`, the article is silent, and the model fabricates. Same
organization, same principle, opposite outcome — decided entirely by whether one field was declared
nullable.

The consequence is worse than a generic fabrication because it is **anti-correlated with safety**: a
fabricated `2024-01-01` makes current financial-distress reporting look two years stale, so a reader
triaging by recency deprioritizes the most urgent item in the briefing — one already flagged
⚠️ ESCALATE for ambiguous supplier identity.

Fix: `source_date: date | None`, a prompt sentence instructing null when the article carries no
publication date, and rendering those claims as `(industry_news, date not stated)`. One type change,
one sentence — converting a silent fabrication into a visible gap.

---

## 6. Five cross-cutting patterns

These recur across all three projects. If you remember nothing else, remember these.

### Pattern 1 — Make absence expressible

**Plain English.** Always give the system a legitimate way to say "I don't know." If you don't, it
will say something else, and that something else will look exactly like knowledge.

**Where it appears:**

| Layer | Mechanism | What it lets the model decline |
|---|---|---|
| Field | `{"type": ["number", "null"]}` | a value |
| Category | `enum: [..., "other"]` + `*_detail` | a classification |
| Document | `flag_for_review` tool alongside the extractor | an entire document |
| Entity | `needs_identifier=true` + `candidates` | an ambiguous match |
| Source | `ReaderResult(ok=False, error=FailureContext(...))` | a whole source |
| Aggregate | `calculated_monthly_total -> None`, not `0.0` | a computed total |
| Check | `IntegrationFinding(status="pass", details="...check skipped")` | a check it couldn't run |

Seven layers, one idea. **A required field is not a guarantee that data exists; it is a guarantee
that something will be in that slot.**

**The counter-example in this very repo** is the sharpest teaching case:
`Claim.source_date: date` is non-nullable, and the model fabricates dates for an undated article
(§5.3). The pattern is easy to state and easy to violate.

### Pattern 2 — Validate what the schema cannot

**Plain English.** Shape-checking is spellcheck. It catches "this should be a number and it's a
string." It cannot catch "this is the wrong number."

**The three failure classes, and what catches each:**

| Class | Example | Caught by |
|---|---|---|
| Malformed shape | `property.address: null` where a string is required | tool schema / Pydantic |
| Arithmetic incoherence | line items sum to 9642.17, stated total 10892.17 | consistency validator |
| **Plausible fabrication** | `{"amount": 0}` on a document with no loan | **neither** |

All three were observed in three consecutive live calls
(`capstone-submission/02-mortgage-extraction/live-vs-replay.txt`). The third class is the one that
requires an *independent* signal — a second model comparing against the source, or a human. No amount
of schema strictness detects a well-formed lie.

### Pattern 3 — Classify failures before reacting to them

**Plain English.** "It failed" is not enough information to decide what to do. *How* it failed
determines whether retrying helps, hurts, or is merely wasteful.

```
format        -> retry with feedback      (misreading; fixable)
consistency   -> retry with feedback      (misreading; fixable)
missing_source-> escalate, zero retries   (absence; retry pressures fabrication)
```

Generalizes well beyond LLM systems, but has extra force here because **retrying an
absence-of-information failure actively pressures the model to fabricate.** In ordinary software a
pointless retry wastes time; here it manufactures wrong data.

The same discipline applied to *sources* in Project 3: `timeout` and `no source reported` land in the
same Incomplete section but carry different annotations, because one is retryable and the other needs
a new source.

### Pattern 4 — Slice every aggregate

**Plain English.** Averages hide exactly the failures you most need to find, because rare categories
are underweighted in an average by definition and rare categories are where models are worst. Those
two facts compound.

```
OVERALL brier=0.291                                        <- "needs some tuning"
umbrella  exclusions  n=2 conf=0.93 acc=0.00 brier=0.865   <- one whole category is broken
```

**The corollary is sampling.** If you slice your metrics but sample uniformly, the rare strata have no
data to slice — you get a cell with `n=0` and learn nothing. Stratified sampling and sliced metrics
are the same idea applied to collection and to analysis; you need both or neither works.

### Pattern 5 — Degrade, don't abort — but know what degradation costs

**Plain English.** When part of the system dies, finish with what's left and state plainly what's
missing. And then check what *else* changed, because "graceful" degradation is rarely neutral.

The mechanism is errors-as-values:

```python
class ReaderResult(BaseModel):
    ok: bool
    claims: list[Claim] = Field(default_factory=list)
    error: FailureContext | None = None
```

The caveat is the second half of the pattern, and the part usually left out: losing the logistics
source turned a ⚠️ ESCALATE contested metric into a Well-Established one at the supplier's own
optimistic figure (§5.3). **Degradation changes conclusions, not just coverage.** Always diff a
degraded run against a healthy one and look at what moved — not just at what disappeared.

---

## 7. Diagrams

### 7.1 The three failure classes and their defenses

```
                          model output
                               │
                    ┌──────────▼───────────┐
                    │  tool schema         │  catches: malformed shape
                    │  (Anthropic API)     │  misses:  valid-but-wrong values
                    └──────────┬───────────┘
                               │  well-formed
                    ┌──────────▼───────────┐
                    │  Pydantic / validator│  catches: illegal values, bad arithmetic
                    │  (domain invariants) │  misses:  arithmetically consistent fiction
                    └──────────┬───────────┘
                               │  valid
                    ┌──────────▼───────────┐
                    │  independent review  │  catches: plausible fabrication
                    │  + integration pass  │  misses:  errors both models share
                    └──────────┬───────────┘
                               │  probably correct
                    ┌──────────▼───────────┐
                    │  HITL routing        │  the residual: a human looks
                    │  + spot-check sample │  + drift detection on the rest
                    └──────────────────────┘

   well-formed  ≠  valid  ≠  correct
   Each layer catches what the one above it structurally cannot.
```

### 7.2 The retry decision

```
                        extract
                           │
                      validate()
                           │
              ┌────────────┼─────────────┐
              │            │             │
           None      format /        missing_source
              │      consistency          │
              ▼            │              ▼
          SUCCESS          │      RetryFutileEscalation
                           │      (ZERO further API calls)
                           ▼
                  attempts < max?
                     │        │
                   yes        no
                     │        │
                     ▼        ▼
          retry with     escalate as
          verbatim       retries_exhausted__<pattern>
          feedback
```

The asymmetry is the point: two categories loop, one exits immediately. Retrying the third would
pressure the model to invent the missing value.

### 7.3 Routing signals

```
   extractor self-confidence ──┐
   (per field, vs 0.90)        │
                               │
   independent reviewer      ──┼──►  ANY one non-empty  ──►  human_review
   (2nd model, no context)     │                             (with `reason` recorded)
                               │
   integration checks        ──┘
   (pure cross-field)          │
                               └──►  ALL three clear    ──►  auto_approve
                                                                  │
                                                    stratified spot-check
                                                    max(1, ceil(pct × n)) per stratum
                                                                  │
                                                                  ▼
                                                             spot_check

   Independence is the design constraint: the reviewer never sees the extractor's
   reasoning, and the integration checks involve no model at all. Signals that
   share a failure mode are one signal wearing three hats.
```

### 7.4 Where each project sits

```
             ┌──────────────────────────────────────────────────────┐
             │  Project 1 — is this ONE output well-formed & valid? │
             │  schema · two-pass tool choice · prompt · consistency │
             └───────────────────────┬──────────────────────────────┘
                                     │  now scale it
             ┌───────────────────────▼──────────────────────────────┐
             │  Project 2 — what do we DO about it, at volume?      │
             │  retry classes · batch+SLA · review · HITL routing   │
             └───────────────────────┬──────────────────────────────┘
                                     │  now add disagreeing sources
             ┌───────────────────────▼──────────────────────────────┐
             │  Project 3 — what if sources CONFLICT or DIE?        │
             │  one claim shape · memory · annotation · degradation │
             └──────────────────────────────────────────────────────┘
```

---

## 8. Anti-patterns and pitfalls

Each of these is a plausible-looking decision that fails in production.

### Schema and prompt

| Anti-pattern | Why it fails | Instead |
|---|---|---|
| Marking a field `required` "so we always get a value" | You get a value. It's invented. | Nullable union; let absence be expressible |
| A closed enum with no `other` | Model picks the nearest wrong value; looks clean, is wrong | `enum + "other" + *_detail` |
| Free-text instead of an enum | Four spellings of one concept; normalization moves downstream | Enum with an overflow bucket |
| One global `required` list across document types | Paystubs grow fabricated property objects | Narrow `required` per document type |
| Few-shot examples without `<reasoning>` | Teaches format, not rationale; doesn't generalize | Every example carries its *why* |
| Paraphrasing a load-bearing prompt rule | Silent behavior change | Pin exact substrings in tests |
| Normalizing downstream | Context is gone; N parsers that disagree; consistency checks impossible | Normalize at extraction |
| `tool_choice={"type":"any"}` with one tool | Identical to a forced call | Register a real alternative (`flag_for_review`) |
| Parsing `response.content[0].text` | Text block is prose; may not exist; ignores the schema | Read the `ToolUseBlock.input` |

### Validation and retry

| Anti-pattern | Why it fails | Instead |
|---|---|---|
| Retrying every failure | Futile on absence — and pressures fabrication | Classify first; escalate `missing_source` |
| Retrying with "that was invalid, try again" | No information to act on | Feed back the verbatim value + specific error |
| Raising an exception for escalation | Callers ignore it until production | A union return type the type checker enforces |
| Zero tolerance on float comparisons | False positives on every OCR rounding artifact; validator gets ignored | A defensible default, overridable per call |
| Returning `0.0` for an empty sum | "No data" becomes "measured zero" | Return `None` |
| Assuming `tool_choice` guarantees conformance | Observed 1 rejection in 3 live calls | Keep Pydantic behind it |
| Trusting a named tolerance constant without probing | `DEFAULT_TOLERANCE_USD = 1.00` enforces $1.005 | Sweep the boundary; test at it |

### Routing and metrics

| Anti-pattern | Why it fails | Instead |
|---|---|---|
| Gating on model confidence alone | Not calibrated (`conf=0.93 acc=0.00`) *and* not load-bearing (removing it changed 0 of 9) | One signal among several |
| A model deciding routing | Unauditable; "the model felt good" isn't an answer to a regulator | Pure function over signals |
| Logging the decision but not the signals | Cannot answer "why" later, and cannot re-derive it from a nondeterministic upstream | Record all signal values at decision time |
| A single aggregate accuracy metric | Hides concentrated failures in rare segments | Slice by `(segment × field)` |
| Uniform random spot-checks | `floor(10%)` of a 3-record stratum is 0 | `max(1, ceil(pct × n))` per stratum |
| Reusing the same model for review | Shared failure modes; "independent" check agrees with the error | A different model, no shared context |
| Letting the reviewer see the extractor's reasoning | Anchoring; checks coherence instead of correctness | Independence enforced by function signature |
| Assuming a seeded pipeline is reproducible | The router is pure and the sampler seeded — the model is neither | Separate the sources of variance and test each |

### Multi-source and resilience

| Anti-pattern | Why it fails | Instead |
|---|---|---|
| Averaging conflicting values | Emits a number no source reported; destroys the finding | Keep both, with source and date |
| Aborting when one source fails | Discards three working sources | Errors as values; annotate the gap |
| One generic "missing" state | Conflates "couldn't ask" with "nobody knew" — different fixes | Distinct annotations per cause |
| Asking an LLM to do the synthesis | Provenance preserved only as reliably as the model felt that day | Deterministic Python over structured claims |
| Storing only embeddings + text | Provenance lost exactly where it matters | Serialize the full record into metadata |
| Merging claims on embedding similarity alone | Over-merges semantically close but distinct metrics | Require embedding neighbourhood **and** token overlap |
| Treating degradation as neutral | A contested metric silently became "Well-Established" at the optimistic value | Diff degraded vs. healthy runs; alert on classification changes caused by coverage loss |
| One relative tolerance for every metric | Noise absorption and business-relevance are different questions | Per-metric tolerances; show the spread even when "corroborated" |

---

## 9. What the runs actually proved

The eight findings from this repo's own evidence pack, because they are the parts that were *observed*
rather than asserted.

| # | Finding | Artifact |
|---|---|---|
| 1 | **`tool_choice` does not guarantee schema conformance.** 1 of 3 identical live calls returned input Pydantic rejected. | `02-mortgage-extraction/live-vs-replay.txt` |
| 2 | **Schema conformance does not guarantee truth.** A different call fabricated `{"amount": 0}` and `{"address": "<UNKNOWN>"}` on a document with neither, and *passed* validation. | same |
| 3 | **Self-reported confidence was neither calibrated nor load-bearing.** `conf=0.93 acc=0.00` in one cell; removing the confidence signal changed 0 of 9 routing outcomes, while removing the reviewer dropped human review from 8 to 1. | `calibration-report.txt`, `D-signal-dominance.txt` |
| 4 | **A deterministic router on a nondeterministic signal is not reproducible.** Two identical live runs, same `--seed 42`: POL-2025-007 moved `spot_check → human_review` because the reviewer changed its mind. | `seed-determinism.txt` |
| 5 | **Graceful degradation changed a conclusion, not just coverage.** Losing logistics promoted a ⚠️ ESCALATE contested metric to "Well-Established" at the supplier's own optimistic 95%. | `timeout-diff.txt` |
| 6 | **A non-nullable required field manufactured evidence.** `source_date: date` on an undated article produced `2024-01-01` live and `2026-03-09` recorded. | `live-vs-offline-briefing.txt` |
| 7 | **A documented tolerance was not the enforced one.** `DEFAULT_TOLERANCE_USD = 1.00` enforces $1.005, because `delta` is rounded to 2dp before the `>` comparison. | `tolerance-boundary-probe.txt` |
| 8 | **The conflict tolerance is asymmetric and does double duty.** Boundary at 86.67 vs 78; a supplier claiming 86% against our measured 78% is badged "corroborated," spread neither shown nor escalated. | `conflict-threshold-sweep.txt` |

Three of these (6, 7, 8) came from deliberately probing a **threshold or a required field** rather
than exercising a happy path. Two more (1, 2) came from running **live** where the offline fixtures
would have been silent. That is the practical lesson about how to find this class of bug: normal
traffic sits far from the boundaries and recorded fixtures hide model variance.

---

## 10. Self-check questions

Answer from memory, then check.

**1. Why is `bonus_monthly: null` better than `bonus_monthly: 0.0` when the paystub has no bonus line?**
<details><summary>Answer</summary>
`0.0` asserts a fact ("earns no bonus"); `null` reports an absence ("document is silent"). An
underwriter acts differently on each. Forcing a value converts a *recoverable gap* — someone could
request more documents — into an *unrecoverable error*, because nothing about `0.0` reveals that it
was manufactured. See §3.1.
</details>

**2. Tool use already guarantees valid JSON. Why keep a consistency validator?**
<details><summary>Answer</summary>
Different guarantees. Schemas constrain **shape**; validators constrain **coherence**. `{"base": 5416.67,
..., "stated_total": 10892.17}` is perfectly schema-valid and arithmetically wrong by $1,250. And
neither catches the third class — plausible fabrication — which needs an independent signal. §6.2.
</details>

**3. Why does a `missing_source` failure escalate with zero retries?**
<details><summary>Answer</summary>
The information isn't in the document, so no reformulation recovers it. Worse: the retry loop appends
"this came back null, try again," and a model that complies must produce a number that isn't there.
Retrying an absence failure is a machine for pressuring fabrication. §4.1.
</details>

**4. Why must the independent reviewer not see the extractor's reasoning?**
<details><summary>Answer</summary>
Anchoring. A reviewer shown a plausible rationale checks whether the reasoning is *coherent*, not
whether the answer is *right* — and coherent wrong answers are the target. Enforced by
`build_review_messages`' signature, which accepts only the document and the extraction. §4.3.
</details>

**5. `OVERALL brier=0.291` looks acceptable. What's wrong?**
<details><summary>Answer</summary>
It averages four well-calibrated samples with two catastrophic ones. Sliced, `umbrella/exclusions`
shows `conf=0.93 acc=0.00 brier=0.865` — one category is completely broken, and high-confidence-plus-
zero-accuracy is the worst combination because it sails through a confidence gate. §2, §4.4.
</details>

**6. Why `max(1, ceil(pct * n))` instead of `round(pct * n)`?**
<details><summary>Answer</summary>
Guarantees every non-empty stratum contributes at least one sample. With `floor`/`round`, a 3-record
umbrella stratum at 10% samples zero — auditing nothing in precisely the category the calibration
report flags as broken. §4.4.
</details>

**7. Two sources report 95% and 78%. Why not average to 86.5%?**
<details><summary>Answer</summary>
86.5% is a number no source reported, describing no state of the world. And the *gap* is the finding:
one is the supplier's self-report, the other our own audit of it. A 17-point spread is a fact about
the relationship, not about delivery. Averaging routes the reader to a performance conversation
instead of a methodology audit. §5.2.
</details>

**8. How does "timeout reading logistics" differ from "no source reported this metric"?**
<details><summary>Answer</summary>
Both are Incomplete; the causes differ. "Couldn't ask" is retryable and the data probably exists.
"Asked, nobody knew" is a coverage gap needing a new source. Same section, different annotations,
different remedies. §5.3.
</details>

**9. The router is a pure function and the sampler is seeded. Is the pipeline reproducible?**
<details><summary>Answer</summary>
No. Both sit on live model calls. Two runs with identical `--seed 42` produced different decisions for
POL-2025-007 because the reviewer changed its verdict. This is why signal values must be *recorded* at
decision time rather than re-derived during an audit. §4.4.
</details>

**10. A source going dark is handled gracefully. What could still go wrong?**
<details><summary>Answer</summary>
The conclusion can change. Losing logistics promoted a contested ⚠️ ESCALATE metric to
"Well-Established" at the supplier's optimistic 95%, and the Contested section went to `_none_`.
Degradation is not neutral — always diff a degraded run against a healthy one. §5.3.
</details>

**11. Where does this codebase violate its own "make absence expressible" rule?**
<details><summary>Answer</summary>
`Claim.source_date: date`, non-nullable and in the tool schema's `required` list. For an article with
no date the model fabricates — `2024-01-01` live, `2026-03-09` recorded. And it fails unsafely: a
fake-stale date makes urgent reporting look old. §5.3.
</details>

**12. Why is `detected_pattern` on `ValidationError` worth its weight?**
<details><summary>Answer</summary>
It converts a failure *count* into a *diagnosis*. `summary.py` aggregates it across a run, so instead
of "5 failures today" you get "5 failures, all `negative_premium`, all from one carrier." One string
field; the cheapest observability feature in the repo. §4.1.
</details>

---

## 11. Applying this to your own work

### The porting checklist

Any workflow where an LLM pulls structured results from messy input:

**Schema (do this first — everything depends on it)**
- [ ] Every field that can be absent is nullable. Justify each non-nullable field out loud.
- [ ] Every categorical has an `other` + `*_detail` overflow.
- [ ] `required` is narrowed per input type, not global.
- [ ] There is a `flag_for_review`-style escape hatch registered alongside the extractor.

**Prompt**
- [ ] One canonical normalization block, interpolated — never duplicated.
- [ ] An explicit anti-fabrication rule, pinned verbatim by a test.
- [ ] Few-shot examples that **contrast** (silent → null *vs.* stated-zero → 0.0), each with
      `<reasoning>`.
- [ ] "Record contradictions, don't fix them."

**Validation**
- [ ] Domain invariants the schema can't express.
- [ ] Failures **classified**, not just detected.
- [ ] A stable `detected_pattern` tag on every failure, aggregated per run.
- [ ] Any redundancy in the source exploited as a checksum.
- [ ] Tolerances **probed at the boundary**, not assumed from the constant.

**Reliability**
- [ ] Retry only recoverable classes; escalate absence immediately.
- [ ] Feedback carries the verbatim prior value and a specific error.
- [ ] Escalation is a return type, not an exception.
- [ ] Sources that can fail return results, not raises.

**Review and routing**
- [ ] An independent check that doesn't share context with the producer.
- [ ] A different model for review than for production, to decorrelate failure modes.
- [ ] Routing is a pure function over ≥2 independent signals; never confidence alone.
- [ ] Every decision records **all** signal values, not just the ones that fired.

**Observability**
- [ ] Metrics sliced by segment; no single aggregate on its own.
- [ ] Spot-check sampling stratified with `max(1, ...)`.
- [ ] Provenance travels on the record, not in the rendering layer.
- [ ] A degraded-vs-healthy diff is part of the test suite.

### Day-one instrumentation

The eight signals worth shipping with v1, each tied to the finding that motivates it:

| Metric | Alert on | Motivated by |
|---|---|---|
| Calibration sliced by `(input_type × field)` — Brier per cell | any cell `acc` far below `conf` | `conf=0.93 acc=0.00` |
| Per-signal firing rate + monthly counterfactual | a signal at 0% (dead check) or ~100% (miscalibrated) | integration fired 0/9 |
| Schema-rejection rate on live tool calls | any sustained non-zero | 1 rejection in 3 |
| Placeholder-value detector (`0`, `"<UNKNOWN>"`, `"N/A"`, epoch dates in fields the source never mentions) | any hit | the fabrication class |
| Escalation rate split by category | `missing_source` rising ⇒ *inputs* changed, not the model | `pattern_summary` |
| Source availability, as a **data-quality** metric | a classification change caused by coverage loss | contested → well-established |
| Spot-check coverage per stratum | any stratum at zero | `floor(10%)` = 0 |
| Signal values logged at decision time, never re-derived | — | same seed, different verdict |

### The one-sentence version

> **Give the system a legitimate way to say "I don't know," check its answers with something that
> doesn't share its blind spots, record why every decision was made at the moment it was made, and
> never trust an average.**

---

## Appendix — Running the systems

```bash
# One venv per final-exercise solution/, from inside that directory
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
```

| System | Directory | Command |
|---|---|---|
| 1 — policy pipeline | `Build a Validated, Routed Insurance Policy Extraction Pipeline/04-hitl-routing/solution/` | `policy-extractor pipeline data/policies/ --routing-out routing_decisions.json --seed 42` |
| 2 — mortgage extraction | `Build a Resilient Mortgage Document Extraction System/04-validate-mathematical-consistency/solution/` | `mortgage-extract fixtures/documents/income_sum_mismatch.txt --mode replay -v` |
| 3 — supply chain | `Investigate Supply Chain Risk with Multi-Source Synthesis/03-resilient-coordinator/solution/` | `supply-chain-investigate meridian --offline [--simulate-timeout]` |

**Verify gates:** `pytest tests/ -v` → 45 passed/3 skipped (offline), 25, and 34 respectively.
`mypy <package>/` and `ruff check <package>/ tests/` clean on all three.

**Two environment notes:**
- System 3's `mypy` needs `--python-version 3.12` on CPython 3.12, because `pyproject.toml` pins 3.11
  while numpy's stubs (via chromadb) use 3.12-only PEP 695 syntax. The error is in a third-party stub,
  not project code.
- System 2's solution README says "28 acceptance tests"; the shipped suite collects and passes 25.

**Offline by default.** Fixtures and recorded responses ship with every stage; `@pytest.mark.live`
tests are outside the verify gate. Set `ANTHROPIC_API_KEY` to run them — and note that the live path
is where several of the findings in §9 came from.

To regenerate the full evidence pack: `capstone-submission/run_all.sh [--live]`.
