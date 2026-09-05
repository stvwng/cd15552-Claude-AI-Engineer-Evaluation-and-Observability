"""JSON Schema for mortgage document extraction.

The schema is a single canonical structure spanning all three document types
(loan application, appraisal, income verification). Per-document-type extractor
tools share these properties but differ in their ``required`` lists.

Nullable fields use the union-type idiom (``type: ["<base>", "null"]``) so the
model can return ``null`` for absent fields rather than fabricating values.
Categorical fields that may grow over time use the ``enum + "other" + *_detail``
pattern: when none of the enum members fit, the model emits ``"other"`` and
writes a free-text reason into the sibling ``_detail`` field.
"""
from __future__ import annotations

from typing import Any

JsonSchema = dict[str, Any]


# Closed-but-extendable categorical value lists. "other" is last in every list
# so the model always has a legal answer for a category the schema does not yet
# cover — without it, an unlisted value gets silently coerced to the nearest
# listed one and the mismatch never surfaces.
PROPERTY_TYPES: list[str] = ["single_family", "condo", "townhouse", "other"]
OCCUPANCY_TYPES: list[str] = ["primary_residence", "second_home", "investment", "other"]
LOAN_PURPOSES: list[str] = ["purchase", "refinance_rate_term", "refinance_cash_out", "other"]


def mortgage_data_schema() -> JsonSchema:
    """Return the canonical JSON Schema for mortgage data extraction.

    The schema is an object with four top-level sub-objects: borrower,
    property, loan, and income. Each sub-object has its own ``properties`` map
    and ``required`` list. The top-level ``required`` list names the
    sub-objects that must always be present.

    Design rules for this schema (these are the LO):

    1. A field that is reliably present in the document goes in the relevant
       sub-object's ``required`` list and has a plain ``type: "<base>"``.
    2. A field that is often absent uses the nullable union idiom:
       ``type: ["<base>", "null"]`` and stays out of ``required``.
    3. A categorical field whose value space will grow over time uses an
       ``enum`` ending in ``"other"`` and is paired with a sibling
       ``*_detail`` string field that captures the free-text spillover when
       the model emits ``"other"``.
    4. Per-document-type ``required`` lists (set by ``tools.doc_type_extractor``
       at extraction time) override the schema's top-level required list. Mark
       only what every document type carries here at the schema level.

    Field names mirror the Pydantic records in :mod:`mortgage_extractor.models`,
    which are declared ``extra="forbid"`` — a property named here that has no
    counterpart there fails validation the moment the model populates it.
    """
    return {
        "type": "object",
        "properties": {
            "borrower": {
                "type": "object",
                "properties": {
                    "full_name": {"type": "string"},
                    "coborrower_name": {"type": ["string", "null"]},
                    "ssn_last4": {
                        "type": ["string", "null"],
                        "description": "Last four digits of the SSN only, never the full number.",
                    },
                    "date_of_birth": {
                        "type": ["string", "null"],
                        "description": "ISO 8601 date (YYYY-MM-DD).",
                    },
                    "email": {"type": ["string", "null"]},
                    "phone": {"type": ["string", "null"]},
                },
                # Only the name is reliably present. Requiring SSN or contact
                # details would force the model to invent them on the many
                # documents that omit them.
                "required": ["full_name"],
            },
            "property": {
                "type": "object",
                "properties": {
                    "address": {"type": "string"},
                    "property_type": {"type": "string", "enum": PROPERTY_TYPES},
                    "property_type_detail": {
                        "type": ["string", "null"],
                        "description": (
                            "Free-text description when property_type is 'other'. "
                            "Null when property_type is a listed value."
                        ),
                    },
                    "occupancy_type": {
                        "type": ["string", "null"],
                        "enum": [*OCCUPANCY_TYPES, None],
                    },
                    "occupancy_type_detail": {
                        "type": ["string", "null"],
                        "description": (
                            "Free-text description when occupancy_type is 'other'."
                        ),
                    },
                    "year_built": {"type": ["integer", "null"]},
                    "gross_living_area_sqft": {"type": ["integer", "null"]},
                    "hoa_dues_monthly": {"type": ["number", "null"]},
                    "appraised_value": {"type": ["number", "null"]},
                },
                "required": ["address", "property_type"],
            },
            "loan": {
                "type": "object",
                "properties": {
                    "amount": {"type": "number"},
                    "term_months": {"type": ["integer", "null"]},
                    "interest_rate": {
                        "type": ["number", "null"],
                        "description": "Decimal rate, e.g. 0.0625 for 6.25%.",
                    },
                    "loan_purpose": {
                        "type": ["string", "null"],
                        "enum": [*LOAN_PURPOSES, None],
                    },
                    "loan_purpose_detail": {
                        "type": ["string", "null"],
                        "description": (
                            "Free-text description when loan_purpose is 'other'."
                        ),
                    },
                    "loan_program": {"type": ["string", "null"]},
                },
                "required": ["amount"],
            },
            "income": {
                "type": "object",
                "properties": {
                    "base_monthly": {"type": ["number", "null"]},
                    "bonus_monthly": {"type": ["number", "null"]},
                    "bonus_ytd": {
                        "type": ["number", "null"],
                        "description": (
                            "Year-to-date bonus. Tracked separately from "
                            "bonus_monthly so a paystub's YTD column can be "
                            "captured even when the current period had no bonus."
                        ),
                    },
                    "commission_monthly": {"type": ["number", "null"]},
                    "overtime_monthly": {"type": ["number", "null"]},
                    "other_monthly": {"type": ["number", "null"]},
                    "stated_monthly_total": {
                        "type": ["number", "null"],
                        "description": (
                            "Total monthly income as stated by the document, "
                            "extracted verbatim. The validator cross-checks this "
                            "against the sum of the per-component fields above."
                        ),
                    },
                },
                # No income field is required: a document that reports income at
                # all reports a different subset every time.
            },
        },
        # Income is omitted here because an appraisal never carries it. Each
        # doc-type extractor narrows this list further via
        # tools._required_sections_for().
        "required": ["borrower", "property", "loan"],
    }


def list_nullable_fields(schema: JsonSchema) -> list[str]:
    """Return dotted paths of every nullable leaf field in the schema.

    A leaf is "nullable" when its declared ``type`` is a list containing
    ``"null"`` (the JSON Schema idiom for union with null). Object-typed
    properties are traversed recursively.
    """
    paths: list[str] = []
    _collect_nullable(schema, prefix="", out=paths)
    return paths


def _collect_nullable(node: JsonSchema, prefix: str, out: list[str]) -> None:
    """Depth-first walk of ``node``'s properties, appending nullable paths."""
    properties = node.get("properties")
    if not isinstance(properties, dict):
        return

    for name, subschema in properties.items():
        if not isinstance(subschema, dict):
            continue
        path = f"{prefix}.{name}" if prefix else name
        declared_type = subschema.get("type")

        if isinstance(declared_type, list) and "null" in declared_type:
            out.append(path)
        elif declared_type == "object":
            _collect_nullable(subschema, prefix=path, out=out)

