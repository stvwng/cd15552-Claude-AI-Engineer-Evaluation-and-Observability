"""Counterfactual over the learner's own routing_decisions.json: which signal carries the load.

Usage:
    python3 signal_dominance.py [path/to/routing_decisions.json]

With no argument the path is resolved relative to THIS FILE (../../01-policy-pipeline/...), so the
script works regardless of the caller's working directory.
"""
import json
import sys
from pathlib import Path

DEFAULT = Path(__file__).resolve().parent.parent.parent / "01-policy-pipeline" / "routing_decisions.json"
path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT

if not path.exists():
    sys.exit(
        f"routing_decisions.json not found at {path}\n"
        "This artifact is produced by the LIVE pipeline run:\n"
        "  policy-extractor pipeline data/policies/ --routing-out routing_decisions.json --seed 42\n"
        "Re-run run_all.sh with --live, or pass the file path as an argument."
    )

rows = json.load(open(path))
sig = {r['policy_id']: {'confidence': bool(r['fields_below_threshold']),
                        'reviewer': bool(r['reviewer_disagreements']),
                        'integration': bool(r['integration_failures'])} for r in rows}
n = len(rows)
print(f"source: {path}   records: {n}\n")
for k in ('confidence', 'reviewer', 'integration'):
    c = sum(1 for s in sig.values() if s[k])
    print(f"{k:13} {c}/{n} ({c/n:.0%})")

base = sum(1 for s in sig.values() if any(s.values()))
print(f"\nas shipped: human_review={base}")
for drop in ('confidence', 'reviewer', 'integration'):
    keep = [k for k in ('confidence', 'reviewer', 'integration') if k != drop]
    print(f"without {drop:12}: human_review={sum(1 for s in sig.values() if any(s[k] for k in keep))}")

solo = [p for p, s in sig.items() if s['reviewer'] and not s['confidence'] and not s['integration']]
print(f"\nreviewer was the ONLY signal on {len(solo)}/{n}: {solo}")
print("These are exactly the records a confidence-only router would have auto-approved.")
