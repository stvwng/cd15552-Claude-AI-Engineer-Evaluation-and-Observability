"""Read-only summary of routing_decisions.json: per-record signals and per-stratum spot-check coverage."""
import json, sys, collections
p = sys.argv[1]
rows = json.load(open(p))
print(f"source: {p}   records: {len(rows)}\n")
hdr = f"{'policy_id':16} {'type':10} {'decision':13} {'minconf':7} {'conf<thr':10} {'reviewer':10} {'integration':11}"
print(hdr); print("-"*len(hdr))
for r in rows:
    cs = r["confidence_summary"]
    mn = min(cs.values()) if cs else float("nan")
    print(f"{r['policy_id']:16} {r['policy_type']:10} {r['decision']:13} {mn:<7.2f} "
          f"{len(r['fields_below_threshold']):<10} {len(r['reviewer_disagreements']):<10} {len(r['integration_failures']):<11}")
print("\n--- which signal(s) fired, per record ---")
for r in rows:
    sigs = []
    if r["fields_below_threshold"]: sigs.append("confidence")
    if r["reviewer_disagreements"]: sigs.append("reviewer")
    if r["integration_failures"]: sigs.append("integration")
    print(f"{r['policy_id']:16} {r['decision']:13} signals={sigs or ['(none — all clear)']}")
print("\n--- stratified spot-check coverage by policy_type ---")
by = collections.defaultdict(lambda: collections.Counter())
for r in rows: by[r["policy_type"]][r["decision"]] += 1
print(f"{'policy_type':12} {'n':>3} {'auto_approve':>13} {'spot_check':>11} {'human_review':>13}")
for t, c in sorted(by.items()):
    n = sum(c.values())
    print(f"{t:12} {n:>3} {c['auto_approve']:>13} {c['spot_check']:>11} {c['human_review']:>13}")
elig = sum(c['auto_approve'] + c['spot_check'] for c in by.values())
print(f"\nspot-check-eligible records (auto_approve before sampling) = {elig}")
print(f"records actually flipped to spot_check                    = {sum(c['spot_check'] for c in by.values())}")
print("\nOnly auto_approve records are eligible for spot-check; human_review records are already")
print("going to a person, so sampling them would be redundant.")
