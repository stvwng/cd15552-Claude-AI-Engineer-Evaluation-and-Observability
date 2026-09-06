"""Probe the None-vs-0.0 design decision in Income.calculated_monthly_total.

The solution README claims: returning None (rather than 0.0) when no components are set is what
keeps an income-less document from silently 'passing' a 0-vs-0 consistency check. This tests it.
"""
from mortgage_extractor.models import Income, MortgageExtraction
from mortgage_extractor.validator import validate

print("A. No income components at all (an appraisal, say) — the shipped behaviour")
empty = Income()
print(f"   calculated_monthly_total = {empty.calculated_monthly_total!r}   <- None, not 0.0")
print(f"   stated_monthly_total     = {empty.stated_monthly_total!r}")
rep = validate(MortgageExtraction(income=empty))
print(f"   validate() -> consistent={rep.consistent}, discrepancies={rep.discrepancies}")
print("   The validator's guard `if calculated is not None and stated is not None` short-circuits.")
print("   Nothing is compared, because there is nothing to compare.\n")

print("B. What would happen if the property returned 0.0 instead of None")
print("   Simulating that by setting the components to zero explicitly:")
zeroed = Income(base_monthly=0.0, stated_monthly_total=0.0)
print(f"   calculated_monthly_total = {zeroed.calculated_monthly_total!r}")
rep2 = validate(MortgageExtraction(income=zeroed))
print(f"   validate() -> consistent={rep2.consistent}")
print("   This reports 'consistent' too — but for the WRONG REASON: it actively compared")
print("   0.0 against 0.0 and found them equal. A document that genuinely failed to extract")
print("   any income would be indistinguishable from one that legitimately has none.\n")

print("C. The case the None design protects: components present, stated absent")
partial = Income(base_monthly=5416.67)
print(f"   calculated_monthly_total = {partial.calculated_monthly_total!r}")
print(f"   stated_monthly_total     = {partial.stated_monthly_total!r}")
rep3 = validate(MortgageExtraction(income=partial))
print(f"   validate() -> consistent={rep3.consistent}")
print("   Also skipped — the document never stated a total, so there is no claim to check")
print("   against. The validator refuses to invent a comparison, exactly as the extractor")
print("   refuses to invent a value.\n")

print("D. Same-unit invariant: only *_monthly components enter the sum")
mixed = Income(base_monthly=5416.67, bonus_monthly=1250.0, bonus_ytd=3500.0)
print(f"   base_monthly=5416.67 bonus_monthly=1250.0 bonus_ytd=3500.0")
print(f"   calculated_monthly_total = {mixed.calculated_monthly_total!r}")
print(f"   = 5416.67 + 1250.0 only. bonus_ytd is a YEAR-TO-DATE figure and is excluded;")
print("   adding it would produce a number in no coherent unit at all.")
