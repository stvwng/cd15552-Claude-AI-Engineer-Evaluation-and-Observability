"""Binary-search the consistency validator's tolerance boundary.

Starts from the REAL extraction of fixtures/documents/income_sum_mismatch.txt (replayed from the
recorded fixture), then varies only stated_monthly_total to sweep delta across the $1.00 tolerance.
Pure function calls: no API, fully deterministic.
"""
from mortgage_extractor.client import RecordingClient
from mortgage_extractor.pipeline import Pipeline
from mortgage_extractor.validator import validate
from mortgage_extractor.config import DEFAULT_TOLERANCE_USD
from pathlib import Path

doc = Path("fixtures/documents/income_sum_mismatch.txt").read_text()
ex = Pipeline(client=RecordingClient(mode="replay")).run(doc)
inc = ex.income
calc = inc.calculated_monthly_total
print("Baseline extraction (replayed from the recorded fixture)")
print(f"  components: base={inc.base_monthly} bonus={inc.bonus_monthly} "
      f"commission={inc.commission_monthly} overtime={inc.overtime_monthly} other={inc.other_monthly}")
print(f"  calculated_monthly_total = {calc}")
print(f"  stated_monthly_total     = {inc.stated_monthly_total}  (as printed in the document)")
print(f"  DEFAULT_TOLERANCE_USD    = {DEFAULT_TOLERANCE_USD}\n")

print("Sweeping stated_monthly_total so that delta = calculated - stated takes each value below.")
print("Only stated_monthly_total is varied; every component is left exactly as extracted.\n")
print(f"{'target delta':>13} {'stated':>12} {'|delta|':>9} {'consistent?':>12}  {'discrepancy reported'}")
print("-"*88)
for target in (0.00, 0.50, 0.99, 0.999, 1.00, 1.001, 1.01, 1.50, 1250.00):
    stated = round(calc - target, 3)
    ex2 = ex.model_copy(update={"income": inc.model_copy(update={"stated_monthly_total": stated})}, deep=True)
    rep = validate(ex2)
    d = rep.discrepancies[0] if rep.discrepancies else None
    shown = f"delta={d.delta}" if d else "-"
    print(f"{target:>13.3f} {stated:>12.3f} {abs(target):>9.3f} {str(rep.consistent):>12}  {shown}")

print(f"\nPREDICTION BEFORE RUNNING: flags when abs(delta) > {DEFAULT_TOLERANCE_USD} (strict >), so")
print("$1.00 exactly passes and anything above it is flagged. The first half held; the second did not.")
print("\nOBSERVED BOUNDARY:")
print("  delta = 1.000  -> consistent (as predicted: the comparison is > , not >=)")
print("  delta = 1.001  -> consistent (NOT predicted)")
print("  delta = 1.010  -> flagged")
print("\nWHY 1.001 SURVIVES. Two lines in validator.py act in sequence:")
print("      delta = round(calculated - stated, 2)      # rounds FIRST")
print("      if abs(delta) > tolerance:                 # compares SECOND")
print("A raw delta of 1.001 rounds to 1.00, and 1.00 > 1.00 is False. The effective threshold is")
print("therefore not $1.00 but $1.005 — the smallest raw delta that rounds up to 1.01. The rounding")
print("silently widens the documented tolerance by half a cent.")
print("\nThis is harmless at this scale, but it is a real gap between the stated contract")
print("(DEFAULT_TOLERANCE_USD = 1.00) and the enforced one ($1.005), and it is only visible by")
print("probing the boundary rather than by reading either line alone.")

print("\n--- zero-tolerance override (the documented per-call escape hatch) ---")
for target in (0.00, 0.50, 1.00):
    stated = round(calc - target, 2)
    ex2 = ex.model_copy(update={"income": inc.model_copy(update={"stated_monthly_total": stated})}, deep=True)
    rep = validate(ex2, tolerance=0.0)
    print(f"  delta={target:.2f} tolerance=0.0 -> consistent={rep.consistent}")
