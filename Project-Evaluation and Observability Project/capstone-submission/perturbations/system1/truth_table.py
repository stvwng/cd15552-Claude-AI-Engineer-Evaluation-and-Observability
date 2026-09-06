"""Deterministic truth table over route_extraction: all 8 signal combinations, no API involved."""
import itertools
from policy_extractor.records import PolicyExtraction, Endorsement
from policy_extractor.reviewer import ReviewResult, FieldAgreement, IntegrationFinding
from policy_extractor.routing import route_extraction, DEFAULT_CONFIDENCE_THRESHOLD

FIELDS = ("policy_type","premium_amount","deductible","coverage_limit","endorsements","exclusions")

def extraction(low_conf):
    conf = {f: 0.99 for f in FIELDS}
    if low_conf: conf["coverage_limit"] = 0.55
    return PolicyExtraction(policy_id="POL-TT", policy_type="auto", premium_amount=1000.0,
        deductible=500.0, coverage_limit=100000.0,
        endorsements=[Endorsement(name="AU-21", limit=40.0)], exclusions=["Racing"],
        premium_components=None, confidence=conf)

def review(disagree):
    ag = {f: FieldAgreement(field=f, agreement="agree", reason=None, review_confidence=0.9) for f in FIELDS}
    if disagree:
        ag["coverage_limit"] = FieldAgreement(field="coverage_limit", agreement="disagree",
                                              reason="document states 250000", review_confidence=0.9)
    return ReviewResult(agreements=ag)

def integ(fail):
    return [IntegrationFinding(check_name="coverage_limit_exceeds_endorsement_sum",
            status="fail" if fail else "pass", details="synthetic control")]

print("DETERMINISTIC TRUTH TABLE FOR route_extraction")
print(f"confidence threshold = {DEFAULT_CONFIDENCE_THRESHOLD}; low-confidence case sets coverage_limit=0.55")
print("All three inputs are constructed directly. No API calls, no model variance.\n")
print(f"{'conf<thr':9} {'reviewer':9} {'integr':7} -> {'DECISION':14} reason")
print("-"*118)
for lc, rd, ig in itertools.product([False,True],repeat=3):
    d = route_extraction(extraction=extraction(lc), review=review(rd), integration_findings=integ(ig))
    print(f"{str(lc):9} {str(rd):9} {str(ig):7} -> {d.decision:14} {d.reason}")
print("\nRULE: the three signals combine with OR, not AND. Any ONE is sufficient to divert to")
print("human_review; auto_approve requires all three clear at once (row 1). The docstring's")
print("'(confidence AND reviewer AND integration)' describes what must hold to AUTO-APPROVE.")
