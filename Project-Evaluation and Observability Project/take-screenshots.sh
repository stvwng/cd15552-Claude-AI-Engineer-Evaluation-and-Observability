#!/usr/bin/env bash
# Prints one screenshot-sized block per system. Run it three times and screenshot each.
#
#   ./take-screenshots.sh 1     # calibration: the aggregate hides a broken cell
#   ./take-screenshots.sh 2     # consistency validator flags a discrepancy, exits 1
#   ./take-screenshots.sh 3     # briefing degrades gracefully when a source dies
#
# Save the images into capstone-submission/0N-*/screenshots/.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
P1="$REPO/Build a Validated, Routed Insurance Policy Extraction Pipeline/04-hitl-routing/solution"
P2="$REPO/Build a Resilient Mortgage Document Extraction System/04-validate-mathematical-consistency/solution"
P3="$REPO/Investigate Supply Chain Risk with Multi-Source Synthesis/03-resilient-coordinator/solution"

bar()  { printf '\033[1m%s\033[0m\n' "════════════════════════════════════════════════════════════════════"; }
head_() { bar; printf '\033[1m %s\033[0m\n' "$1"; printf ' %s\n' "$2"; bar; echo; }

case "${1:-}" in
1)
  head_ "SYSTEM 1 — sliced calibration report" \
        "save to: capstone-submission/01-policy-pipeline/screenshots/"
  cd "$P1"
  echo "\$ .venv/bin/python calibration_report.py"; echo
  .venv/bin/python calibration_report.py
  echo
  echo "  ^ umbrella/exclusions: 93% confident, 0% accurate (cell Brier 0.865)"
  echo "    while OVERALL Brier reads only 0.291. The average hides the broken cell."
  ;;
2)
  head_ "SYSTEM 2 — consistency validator flags a discrepancy" \
        "save to: capstone-submission/02-mortgage-extraction/screenshots/"
  cd "$P2"
  echo "\$ .venv/bin/mortgage-extract fixtures/documents/income_sum_mismatch.txt --mode replay -v"; echo
  env -u ANTHROPIC_API_KEY .venv/bin/mortgage-extract \
      fixtures/documents/income_sum_mismatch.txt --mode replay -v 2>&1 \
    | grep -E "classify:|extract:|\"consistent\"|\"field\"|\"calculated\"|\"stated\"|\"delta\""
  code=${PIPESTATUS[0]}
  echo
  echo "\$ echo \$?"
  echo "$code   <-- non-zero because the document's stated total disagrees with its own line items"
  echo
  echo "  ^ two-pass classify-then-extract visible in the log; delta -1250.00 is exactly the bonus."
  ;;
3)
  head_ "SYSTEM 3 — graceful degradation when a source goes dark" \
        "save to: capstone-submission/03-supply-chain/screenshots/"
  cd "$P3"
  echo "\$ .venv/bin/supply-chain-investigate meridian --offline --simulate-timeout"; echo
  env -u ANTHROPIC_API_KEY .venv/bin/supply-chain-investigate meridian --offline --simulate-timeout 2>/dev/null \
    | grep -E "^# |^> Sources|^## |missing source|_none_|on_time_delivery_rate|late_shipment_count"
  echo
  echo "  ^ run completes (exit 0) with the dead source named at the top."
  echo "    'timeout reading logistics' vs 'no source reported this metric' are kept distinct."
  ;;
*)
  echo "usage: ./take-screenshots.sh {1|2|3}"; exit 2 ;;
esac
echo
