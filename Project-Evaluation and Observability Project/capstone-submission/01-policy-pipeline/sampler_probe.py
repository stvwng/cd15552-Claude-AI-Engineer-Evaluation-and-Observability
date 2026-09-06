"""Controlled probe of apply_stratified_spot_check: isolate the seed from live model variance.

Calls the REAL shipped function. The decision set is synthetic and clearly labelled, because the
live corpus yielded only one spot-check-eligible record, which cannot exercise seed behaviour.
"""
from policy_extractor.routing import RoutingDecision, apply_stratified_spot_check
import collections

def mk(pid, ptype):
    return RoutingDecision(policy_id=pid, policy_type=ptype, decision="auto_approve",
                           reason="all clear", fields_below_threshold=[], reviewer_disagreements=[],
                           integration_failures=[], confidence_summary={"premium_amount": 0.99})

# Deliberately unequal strata: a naive uniform 10% sample would round umbrella (3) and other (1) to zero.
strata = {"auto": 20, "home": 12, "umbrella": 3, "other": 1}
decisions = [mk(f"{t.upper()}-{i:03d}", t) for t, n in strata.items() for i in range(n)]
print(f"synthetic decision set: {len(decisions)} auto_approve records")
print(f"strata sizes: {strata}\n")

def picks(seed, pct=0.10):
    out = apply_stratified_spot_check(decisions, sample_pct=pct, seed=seed)
    return sorted(d.policy_id for d in out if d.decision == "spot_check")

print("=== A. Seed determinism: same seed => same selection ===")
p42a, p7, p42b, p99 = picks(42), picks(7), picks(42), picks(99)
print(f"seed=42 (1st): {p42a}")
print(f"seed=42 (2nd): {p42b}")
print(f"seed=42 reproduces byte-for-byte: {p42a == p42b}")
print(f"seed=7       : {p7}")
print(f"seed=99      : {p99}")
print(f"seed 7 differs from seed 42 (the seed genuinely drives selection): {p7 != p42a}")

print("\n=== B. Stratum preservation: no stratum with eligible records is ever dropped ===")
import math
print(f"{'stratum':10} {'n':>3} {'naive floor(10%)':>17} {'ceil(10%) shipped':>18} {'actually picked':>16}")
for seed in (42, 7, 99):
    sel = picks(seed)
    c = collections.Counter(pid.split('-')[0].lower() for pid in sel)
    print(f"-- seed={seed}")
    for t, n in strata.items():
        key = t[:20]
        print(f"{t:10} {n:>3} {math.floor(0.10*n):>17} {max(1, math.ceil(0.10*n)):>18} {c[t]:>16}")
    missed = [t for t in strata if c[t] == 0]
    print(f"   strata with zero coverage: {missed or 'NONE'}")

print("\n=== C. Why this matters ===")
print("Under naive floor(10%) sampling, 'umbrella' (n=3) and 'other' (n=1) sample ZERO records —")
print("the two rarest policy types would never be audited, which is precisely where model drift")
print("hides. The shipped max(1, ceil(...)) rule guarantees every non-empty stratum is covered.")
