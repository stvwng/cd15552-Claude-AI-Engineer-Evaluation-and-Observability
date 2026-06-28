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


# TODO: Define the closed-but-extendable categorical value lists. Each list is
# an enum that the model will pick from. The final entry of every list must be
# "other" so the model has a legal escape hatch when the document names a
# category the schema does not yet cover.
PROPERTY_TYPES: list[str] = []  # TODO: e.g. single_family, condo, townhouse, ..., other
OCCUPANCY_TYPES: list[str] = []  # TODO: e.g. primary_residence, second_home, investment, other
LOAN_PURPOSES: list[str] = []  # TODO: e.g. purchase, refinance_rate_term, refinance_cash_out, other


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
    """
    # TODO: Build and return the JSON Schema dictionary per the design rules
    # in this docstring. At minimum, satisfy these acceptance criteria from
    # the PRD (also enforced by tests/test_us01_schema.py):
    #
    #   - top-level type is "object" with a non-empty properties map.
    #   - borrower.full_name, property.address, and loan.amount are
    #     each required in their sub-object. Optional fields like
    #     borrower.coborrower_name and property.year_built live in
    #     properties but NOT in required.
    #   - at least one categorical field uses enum: [..., "other"]
    #     paired with a sibling *_detail string field.
    #   - at least three fields the document frequently omits are
    #     typed as ["<base>", "null"] — e.g. borrower.coborrower_name,
    #     property.hoa_dues_monthly, income.bonus_ytd.
    #
    # See the build-friction notes: every entry in a per-document-type
    # `required` list is a license to fabricate when the document is silent.
    # Be deliberate about what you require.
    raise NotImplementedError("Exercise 1: implement mortgage_data_schema()")


def list_nullable_fields(schema: JsonSchema) -> list[str]:
    """Return dotted paths of every nullable leaf field in the schema.

    A leaf is "nullable" when its declared ``type`` is a list containing
    ``"null"`` (the JSON Schema idiom for union with null). Object-typed
    properties are traversed recursively.
    """
    # TODO: Walk the schema and collect dotted paths of every leaf whose
    # declared type list includes "null". For example, if income.bonus_ytd has
    # type ["number", "null"], emit "income.bonus_ytd". Recurse into nested
    # object-typed properties. Every returned path
    # resolves via cursor = schema["properties"][segment] for each segment.
    raise NotImplementedError("Exercise 1: implement list_nullable_fields()")
