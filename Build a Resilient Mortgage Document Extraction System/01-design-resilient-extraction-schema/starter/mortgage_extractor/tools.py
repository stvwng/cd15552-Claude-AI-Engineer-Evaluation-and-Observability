"""Anthropic tool definitions for the mortgage extraction pipeline.

A "tool" in the Anthropic Messages API is a JSON object with a ``name``,
``description``, and ``input_schema`` (JSON Schema). When the API returns a
``tool_use`` content block, its ``input`` is guaranteed to validate against
this schema, which is how this project enforces structured output.

The canonical extractor tool, :func:`extract_mortgage_data`, will be registered
for the second pass of the pipeline in Exercise 2. The classifier tool,
:func:`classify_document`, will be registered for the forced first pass. Both
share the schema you build in :mod:`mortgage_extractor.schema`.
"""
from __future__ import annotations

from typing import TypedDict

from mortgage_extractor.models import DocumentType
from mortgage_extractor.schema import JsonSchema, mortgage_data_schema


class ToolDefinition(TypedDict):
    name: str
    description: str
    input_schema: JsonSchema


# The two rules below are the whole point of the schema design: without them
# the model treats an absent field as an invitation to guess, and an unlisted
# enum value as a reason to pick the closest listed one. Repeated verbatim on
# every extractor tool so a doc-type-specific tool is never the weaker prompt.
_EXTRACTION_RULES = (
    "Use null for any field the document does not explicitly state — do not "
    "infer, default, or fabricate a value. When a categorical field's value is "
    "not one of the listed enum members, emit 'other' and write the document's "
    "actual wording into the sibling *_detail field."
)


def extract_mortgage_data() -> ToolDefinition:
    """Return the canonical mortgage-data extractor tool definition.

    The tool's input_schema is the full mortgage_data_schema. The description
    is the model's read-once instruction sheet for what the tool extracts.
    """
    return {
        "name": "extract_mortgage_data",
        "description": (
            "Extract structured mortgage data (borrower, property, loan, and "
            f"income details) from a single mortgage document. {_EXTRACTION_RULES}"
        ),
        "input_schema": mortgage_data_schema(),
    }


def classify_document() -> ToolDefinition:
    """Return the document-classifier tool definition.

    The classifier returns one of the four supported document types plus a
    one-sentence reason. The reason is what surfaces in
    ``UnsupportedDocumentTypeError`` when the type is ``"other"``.
    """
    return {
        "name": "classify_document",
        "description": (
            "Classify a mortgage document as loan_application, appraisal, "
            "income_verification, or other. Choose 'other' when none of the "
            "three supported types apply, and always give a one-sentence "
            "reason naming the textual cues that drove the choice."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "document_type": {
                    "type": "string",
                    "enum": [
                        "loan_application",
                        "appraisal",
                        "income_verification",
                        "other",
                    ],
                },
                "reason": {
                    "type": "string",
                    "description": (
                        "One sentence describing the textual cues that drove "
                        "the classification."
                    ),
                },
            },
            "required": ["document_type", "reason"],
        },
    }


def doc_type_extractor(doc_type: DocumentType) -> ToolDefinition:
    """Return a doc-type-tailored extractor tool.

    The canonical schema is shared across document types. This function
    narrows the schema's ``required`` list to the sections a given document
    type is expected to carry, so each extractor tool only forces the model
    to populate the sections that document type actually contains.

    Friction-notes warning: every entry in the per-type required list is a
    license to fabricate when the document is silent. Pick what each document
    type *carries*, not what would be nice to have.
    """
    # mortgage_data_schema() builds a fresh dict per call, so narrowing
    # `required` here cannot leak into another doc type's tool.
    schema = mortgage_data_schema()
    schema["required"] = _required_sections_for(doc_type)
    return {
        "name": f"extract_{doc_type.value}",
        "description": (
            f"Extract structured mortgage data from a {doc_type.value} "
            f"document. {_EXTRACTION_RULES}"
        ),
        "input_schema": schema,
    }


def flag_for_review() -> ToolDefinition:
    """Return the escape-hatch tool the model calls when it cannot extract.

    Registered alongside the doc-type-specific extractor for Exercise 2's
    ``tool_choice="any"`` extraction pass. The presence of this second tool
    is what makes ``"any"`` meaningful — with only one tool registered, the
    API behaves the same as forced.
    """
    return {
        "name": "flag_for_review",
        "description": (
            "Call this instead of an extractor when the document is too "
            "unclear, damaged, or off-topic to extract confidently. Provide a "
            "one-sentence reason so a human reviewer knows what went wrong."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": (
                        "One sentence describing why extraction is not possible."
                    ),
                },
            },
            "required": ["reason"],
        },
    }


def _required_sections_for(doc_type: DocumentType) -> list[str]:
    """Which top-level sections must appear in the extractor's output.

    A loan application document carries borrower, property, and loan details
    together. An appraisal centres on the property. An income-verification
    document identifies the borrower and reports their income; it typically
    does not state the loan amount or describe the property.
    """
    match doc_type:
        case DocumentType.LOAN_APPLICATION:
            return ["borrower", "property", "loan"]
        case DocumentType.APPRAISAL:
            return ["property"]
        case DocumentType.INCOME_VERIFICATION:
            return ["borrower", "income"]
        case DocumentType.OTHER:
            raise ValueError(
                "doc_type_extractor should never be called with "
                "DocumentType.OTHER; Exercise 2 short-circuits at classify time."
            )
        case _:
            raise ValueError(f"Unknown document type: {doc_type!r}")


__all__ = [
    "ToolDefinition",
    "classify_document",
    "doc_type_extractor",
    "extract_mortgage_data",
    "flag_for_review",
]
