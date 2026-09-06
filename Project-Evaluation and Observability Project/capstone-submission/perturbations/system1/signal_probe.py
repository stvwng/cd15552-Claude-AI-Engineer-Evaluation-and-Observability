"""Route one document end-to-end and report WHICH of the three routing signals fired.

Uses the shipped extract_with_retry / independent_review / integration_pass / route_extraction.
"""
import json, sys
from pathlib import Path
from anthropic import Anthropic
from policy_extractor.client import AnthropicMessagesClient
from policy_extractor.records import PolicyExtraction, RetryFutileEscalation
from policy_extractor.retry import extract_with_retry
from policy_extractor.reviewer import independent_review, integration_pass
from policy_extractor.routing import route_extraction

path = Path(sys.argv[1]); pid = sys.argv[2]
doc = path.read_text()
client = AnthropicMessagesClient(Anthropic())
outcome = extract_with_retry(client=client, policy_id=pid, document_text=doc, max_retries=3)
print(f"document: {path.name}")
if isinstance(outcome, RetryFutileEscalation):
    print(f"ESCALATED before routing: field={outcome.field} category={outcome.category} pattern={outcome.detected_pattern}")
    raise SystemExit(0)

review = independent_review(client=client, source_document=doc, extracted_record={
    "policy_id": outcome.policy_id, "policy_type": outcome.policy_type,
    "premium_amount": outcome.premium_amount, "deductible": outcome.deductible,
    "coverage_limit": outcome.coverage_limit,
    "endorsements": [{"name": e.name, "limit": e.limit} for e in (outcome.endorsements or [])],
    "exclusions": outcome.exclusions})
integ = integration_pass(outcome)
d = route_extraction(extraction=outcome, review=review, integration_findings=integ)

print(f"\nextracted coverage_limit = {outcome.coverage_limit}")
print(f"extracted endorsements   = {[(e.name, e.limit) for e in (outcome.endorsements or [])]}")
print("\n--- integration checks ---")
for f in integ:
    print(f"  [{f.status.upper():4}] {f.check_name}: {f.details}")
print("\n--- ROUTING SIGNALS ---")
print(f"  confidence  : fields_below_threshold = {d.fields_below_threshold}")
print(f"  reviewer    : disagreements          = {d.reviewer_disagreements}")
print(f"  integration : failures               = {d.integration_failures}")
fired = [n for n, v in (("confidence", d.fields_below_threshold), ("reviewer", d.reviewer_disagreements), ("integration", d.integration_failures)) if v]
print(f"\n  SIGNALS FIRED : {fired or ['(none)']}")
print(f"  DECISION      : {d.decision}")
print(f"  REASON        : {d.reason}")
