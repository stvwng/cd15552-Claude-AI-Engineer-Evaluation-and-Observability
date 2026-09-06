#!/usr/bin/env bash
# Rebuild the entire evidence pack from a clean checkout.
#
#   ./run_all.sh            # offline only (no API key needed)
#   ./run_all.sh --live     # additionally run the live captures
#
# Offline mode reproduces every artifact that does not require the Anthropic API. Live mode adds the
# end-to-end pipeline run, the live/replay comparison, and the live news extraction. Live outputs are
# expected to DIFFER between runs — that non-determinism is itself a documented finding.
#
# WHAT THIS SCRIPT DOES NOT REGENERATE. Four documents in the pack are hand-authored analysis, not
# tool output, and this script deliberately leaves them untouched:
#     reflection-brief.md      perturbation-log.md      evidence-index.md
# It also leaves the annotated narrative captures alone — 03-supply-chain/timeout-diff.txt,
# 03-supply-chain/live-vs-offline-briefing.txt, 02-mortgage-extraction/live-vs-replay.txt and
# 01-policy-pipeline/seed-determinism.txt each wrap raw tool output in written interpretation.
# The script regenerates their RAW inputs with a .raw extension so the underlying data can be
# re-derived and compared, without overwriting the prose built on top of it.

set -uo pipefail

LIVE=0
[[ "${1:-}" == "--live" ]] && LIVE=1

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"

P1="$REPO/Build a Validated, Routed Insurance Policy Extraction Pipeline/04-hitl-routing/solution"
P2="$REPO/Build a Resilient Mortgage Document Extraction System/04-validate-mathematical-consistency/solution"
P3="$REPO/Investigate Supply Chain Risk with Multi-Source Synthesis/03-resilient-coordinator/solution"

say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
off() { env -u ANTHROPIC_API_KEY "$@"; }   # force the offline path

# ---------------------------------------------------------------- 0. environments
say "Phase 0 — virtualenvs"
for D in "$P1" "$P2" "$P3"; do
  if [[ ! -x "$D/.venv/bin/python" ]]; then
    echo "creating venv in $D"
    python3 -m venv "$D/.venv"
    "$D/.venv/bin/pip" install -q --upgrade pip
    ( cd "$D" && .venv/bin/pip install -e ".[dev]" >/dev/null )
  else
    echo "venv present: $D"
  fi
done
# Warm the embedding model so timings measure compute, not a one-off download.
off "$P3/.venv/bin/python" -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')" >/dev/null 2>&1

{
  echo "captured: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  sw_vers 2>/dev/null || uname -a
  python3 --version
  echo "git rev: $(git -C "$REPO" rev-parse HEAD)"
} > "$HERE/environment.txt"
for D in "$P1" "$P2" "$P3"; do
  { echo; echo "== pip freeze: $D"; "$D/.venv/bin/pip" freeze; } >> "$HERE/environment.txt"
done

# ---------------------------------------------------------------- 1. verify
say "Phase 1 — test suites and static analysis"
run_checks() {  # <dir> <package> <outdir>
  local D="$1" PKG="$2" O="$3"
  ( cd "$D"
    { echo "\$ pytest tests/ -v"; off .venv/bin/pytest tests/ -v; echo "exit=$?"
      echo; echo "-- rerun (determinism) --"; off .venv/bin/pytest tests/ -v; echo "exit=$?"
    } > "$O/tests.txt" 2>&1
    { echo "\$ mypy $PKG"
      if [[ "$PKG" == "supply_chain_risk/" ]]; then
        .venv/bin/mypy --python-version 3.12 "$PKG"; echo "exit=$?"
      else
        .venv/bin/mypy "$PKG"; echo "exit=$?"
      fi
      echo; echo "\$ ruff check $PKG tests/"; .venv/bin/ruff check "$PKG" tests/; echo "exit=$?"
    } > "$O/static-checks.txt" 2>&1 )
}
run_checks "$P1" "policy_extractor/"   "$HERE/01-policy-pipeline"
run_checks "$P2" "mortgage_extractor/" "$HERE/02-mortgage-extraction"
run_checks "$P3" "supply_chain_risk/"  "$HERE/03-supply-chain"
grep -hE "passed|exit=" "$HERE"/0*/tests.txt | grep -E "passed" || true

# ---------------------------------------------------------------- 2. offline behaviour
say "Phase 2 — offline behaviour captures"

( cd "$P1"
  cp "$HERE/../calibration_report.py" . 2>/dev/null || true
  { echo "\$ python calibration_report.py"; .venv/bin/python calibration_report.py; echo "exit=$?"; } \
    > "$HERE/01-policy-pipeline/calibration-report.txt" 2>&1
  off .venv/bin/pytest tests/test_us04_routing.py -v > "$HERE/01-policy-pipeline/routing-tests.txt" 2>&1 )

( cd "$P2"
  for F in appraisal_informal_sqft income_missing_bonus income_sum_mismatch; do
    case $F in
      appraisal_informal_sqft) OUT=extract-run.txt ;;
      income_missing_bonus)    OUT=missing-field-run.txt ;;
      income_sum_mismatch)     OUT=discrepancy-run.txt ;;
    esac
    { echo "\$ mortgage-extract fixtures/documents/$F.txt --mode replay -v"
      off .venv/bin/mortgage-extract "fixtures/documents/$F.txt" --mode replay -v
      echo "exit=$?"
    } > "$HERE/02-mortgage-extraction/$OUT" 2>&1
  done )

( cd "$P3"
  off .venv/bin/supply-chain-investigate meridian --offline                    > "$HERE/03-supply-chain/briefing.md"         2>/dev/null
  off .venv/bin/supply-chain-investigate meridian --offline --simulate-timeout > "$HERE/03-supply-chain/briefing-timeout.md" 2>/dev/null
  { echo "\$ supply-chain-investigate meridian --offline"; echo; cat "$HERE/03-supply-chain/briefing.md"; } \
    > "$HERE/03-supply-chain/investigation-run.txt"
  { echo "\$ supply-chain-investigate meridian --offline --simulate-timeout"; echo; cat "$HERE/03-supply-chain/briefing-timeout.md"; } \
    > "$HERE/03-supply-chain/timeout-run.txt"
  diff "$HERE/03-supply-chain/briefing.md" "$HERE/03-supply-chain/briefing-timeout.md" \
    > "$HERE/03-supply-chain/timeout-diff.raw" 2>&1 || true )

# ---------------------------------------------------------------- 3. offline perturbations
say "Phase 3 — offline perturbation probes"
( cd "$P1"
  .venv/bin/python "$HERE/perturbations/system1/truth_table.py"  > "$HERE/perturbations/system1/C-routing-truth-table.txt" 2>&1
  .venv/bin/python "$HERE/01-policy-pipeline/sampler_probe.py"   > "$HERE/01-policy-pipeline/sampler-seed-probe.txt"      2>&1 )
( cd "$P2"
  off .venv/bin/python "$HERE/perturbations/system2/tolerance_probe.py" > "$HERE/perturbations/system2/tolerance-boundary-probe.txt" 2>&1
  off .venv/bin/python "$HERE/perturbations/system2/null_probe.py"      > "$HERE/perturbations/system2/null-vs-zero-probe.txt"      2>&1 )

# ---------------------------------------------------------------- 4. live (optional)
if [[ $LIVE -eq 1 ]]; then
  say "Phase 4 — LIVE captures (requires ANTHROPIC_API_KEY)"
  : "${ANTHROPIC_API_KEY:?set ANTHROPIC_API_KEY or omit --live}"

  ( cd "$P1"
    { echo "\$ policy-extractor pipeline data/policies/ --routing-out routing_decisions.json --spot-check-pct 0.1 --seed 42"
      .venv/bin/policy-extractor pipeline data/policies/ \
        --routing-out routing_decisions.json --spot-check-pct 0.1 --seed 42
      echo "exit=$?"
    } > "$HERE/01-policy-pipeline/pipeline-run.txt" 2>&1
    cp routing_decisions.json "$HERE/01-policy-pipeline/" 2>/dev/null || true
    python3 "$HERE/01-policy-pipeline/summarize_routing.py" routing_decisions.json \
      > "$HERE/01-policy-pipeline/stratum-coverage.txt" 2>&1 || true
    .venv/bin/python "$HERE/perturbations/system1/signal_probe.py" \
      data/policies/POL-2025-001.txt POL-2025-001 \
      > "$HERE/perturbations/system1/B-baseline-signals.txt" 2>/dev/null || true
    .venv/bin/python "$HERE/perturbations/system1/signal_probe.py" \
      "$HERE/perturbations/system1/POL-2025-001-endorsement-exceeds-coverage.txt" POL-2025-001-INTEG \
      > "$HERE/perturbations/system1/B-perturbed-integration-signals.txt" 2>/dev/null || true
    .venv/bin/policy-extractor extract data/policies/POL-2025-001.txt \
      --policy-id POL-2025-001 \
      > "$HERE/perturbations/system1/A-baseline-unperturbed.json" \
      2> "$HERE/perturbations/system1/A-baseline-unperturbed.stderr" || true
    .venv/bin/policy-extractor extract \
      "$HERE/perturbations/system1/POL-2025-001-premium-blanked.txt" \
      --policy-id POL-2025-001-PERTURBED --max-retries 3 \
      > "$HERE/perturbations/system1/A-perturbed-premium-blanked.json" \
      2> "$HERE/perturbations/system1/A-perturbed-premium-blanked.stderr" || true )

  ( cd "$P2"
    .venv/bin/python "$HERE/perturbations/system2/live_vs_replay.py" \
      fixtures/documents/income_sum_mismatch.txt 3 \
      > "$HERE/02-mortgage-extraction/live-vs-replay.raw" 2>&1 || true )

  ( cd "$P3"
    .venv/bin/supply-chain-investigate meridian > "$HERE/03-supply-chain/briefing-live.md" 2>/dev/null || true
    diff "$HERE/03-supply-chain/briefing.md" "$HERE/03-supply-chain/briefing-live.md" \
      > "$HERE/03-supply-chain/live-vs-offline.raw" 2>&1 || true )
else
  say "Skipping live captures (pass --live to include them)"
fi

# ---------------------------------------------------------------- 5. derived from live artifacts
# signal_dominance reads routing_decisions.json, which only the LIVE pipeline produces. It runs here,
# after phase 4, so a --live run in this same invocation satisfies it; a file left by an earlier live
# run also works.
say "Signal-dominance counterfactual"
if [[ -f "$HERE/01-policy-pipeline/routing_decisions.json" ]]; then
  if python3 "$HERE/perturbations/system1/signal_dominance.py" \
       > "$HERE/perturbations/system1/D-signal-dominance.txt" 2>&1; then
    echo "regenerated -> perturbations/system1/D-signal-dominance.txt"
    grep -E "^(confidence|reviewer|integration) " "$HERE/perturbations/system1/D-signal-dominance.txt" || true
  else
    echo "FAILED (see D-signal-dominance.txt)"
  fi
else
  echo "skipped — 01-policy-pipeline/routing_decisions.json absent (re-run with --live)"
fi

# ---------------------------------------------------------------- 6. corpus integrity
say "Corpus integrity check"
if [[ -z "$(git -C "$REPO" status --porcelain -- '*/fixtures/*' '*/data/*')" ]]; then
  echo "OK — no bundled fixture or data file was modified."
else
  echo "WARNING — bundled corpus files show modifications:"
  git -C "$REPO" status --porcelain -- '*/fixtures/*' '*/data/*'
fi

say "Done. Artifacts under $HERE"
