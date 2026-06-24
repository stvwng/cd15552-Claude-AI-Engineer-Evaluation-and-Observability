"""Validates extracted policy records and categorises failures.

The validator only handles semantic and consistency errors. JSON-syntax errors
are eliminated upstream by tool_choice-forced structured tool calls — the SDK
enforces the schema before this validator runs.
"""
from __future__ import annotations

from typing import Any

from policy_extractor.records import ValidationError


def validate_extraction(extraction: dict[str, Any]) -> ValidationError | None:
    """Return the first ValidationError found, or None if extraction is clean.

    Checks run in this order:
      1. Required fields absent (null) → missing_source
      2. Numeric fields out of legal range (negative premium, etc.) → format
      3. Cross-field consistency (premium vs sum of components) → consistency
    """
    # TODO: Run the three checks in order and return the first error found
    # (or None when all three pass).
    raise NotImplementedError("LO-A — implement validate_extraction.")


_REQUIRED_FIELDS = ("premium_amount", "deductible", "coverage_limit", "endorsements", "exclusions")


def _check_required_present(extraction: dict[str, Any]) -> ValidationError | None:
    """Return missing_source ValidationError for the first null required field, else None."""
    # TODO: For each field in _REQUIRED_FIELDS, if extraction.get(field) is None
    # return a ValidationError with category="missing_source" and
    # detected_pattern=f"{field}_absent". The message should explain that retry is
    # futile because the source document does not contain this information.
    raise NotImplementedError("LO-A — implement _check_required_present.")


def _check_numeric_ranges(extraction: dict[str, Any]) -> ValidationError | None:
    """Return format ValidationError for any negative numeric field, else None."""
    # TODO: Reject negative premium_amount, deductible, coverage_limit.
    # Use detected_patterns "negative_premium", "negative_deductible",
    # "negative_coverage_limit". category="format" — these are recoverable, so the
    # retry loop should feed the offending value back to the model.
    raise NotImplementedError("LO-A — implement _check_numeric_ranges.")


def _check_premium_components_consistency(
    extraction: dict[str, Any],
) -> ValidationError | None:
    """Return consistency ValidationError when stated premium ≠ sum(components), else None."""
    # TODO: If premium_components is non-empty AND premium_amount is a number,
    # compare sum(components.amount) to premium_amount and emit a consistency error
    # when they diverge.
    #
    # ⚠ Use a tolerance on the comparison (e.g., abs(delta) > 0.01) — components
    # carry cents and strict floating-point equality will fire false positives on
    # every itemised policy. detected_pattern="premium_does_not_match_components".
    raise NotImplementedError("LO-A — implement _check_premium_components_consistency.")
