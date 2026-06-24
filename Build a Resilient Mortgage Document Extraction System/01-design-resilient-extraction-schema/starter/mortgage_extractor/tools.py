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


def extract_mortgage_data() -> ToolDefinition:
    """Return the canonical mortgage-data extractor tool definition.

    The tool's input_schema is the full mortgage_data_schema. The description
    is the model's read-once instruction sheet for what the tool extracts.
    """
    # TODO: Return a ToolDefinition with:
    #   - name: "extract_mortgage_data"
    #   - description: a short paragraph that names the tool's job AND
    #     instructs the model to (a) emit null for fields the document does
    #     not state, and (b) emit "other" plus a *_detail value when a
    #     categorical enum value does not fit.
    #   - input_schema: the result of mortgage_data_schema()
    raise NotImplementedError("Exercise 1: implement extract_mortgage_data()")


def classify_document() -> ToolDefinition:
    """Return the document-classifier tool definition.

    The classifier returns one of the four supported document types plus a
    one-sentence reason. The reason is what surfaces in
    ``UnsupportedDocumentTypeError`` when the type is ``"other"``.
    """
    # TODO: Return a ToolDefinition with:
    #   - name: "classify_document"
    #   - description: short instruction to classify into loan_application,
    #     appraisal, income_verification, or other.
    #   - input_schema: an object schema with a "document_type" enum field
    #     (the four values above) and a "reason" string field; both required.
    raise NotImplementedError("Exercise 1: implement classify_document()")


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
    # TODO: Build a ToolDefinition whose:
    #   - name is f"extract_{doc_type.value}"
    #   - description tells the model this is the {doc_type} extractor and
    #     repeats the null / "other" + *_detail rules
    #   - input_schema is mortgage_data_schema() with its top-level "required"
    #     list narrowed by _required_sections_for(doc_type)
    raise NotImplementedError("Exercise 1: implement doc_type_extractor()")


def flag_for_review() -> ToolDefinition:
    """Return the escape-hatch tool the model calls when it cannot extract.

    Registered alongside the doc-type-specific extractor for Exercise 2's
    ``tool_choice="any"`` extraction pass. The presence of this second tool
    is what makes ``"any"`` meaningful — with only one tool registered, the
    API behaves the same as forced.
    """
    # TODO: Return a ToolDefinition named "flag_for_review" with a "reason"
    # string field in input_schema (required).
    raise NotImplementedError("Exercise 1: implement flag_for_review()")


def _required_sections_for(doc_type: DocumentType) -> list[str]:
    """Which top-level sections must appear in the extractor's output.

    A loan application document carries borrower, property, and loan details
    together. An appraisal centres on the property. An income-verification
    document identifies the borrower and reports their income; it typically
    does not state the loan amount or describe the property.
    """
    # TODO: Return the required-sections list for each DocumentType:
    #   LOAN_APPLICATION -> ["borrower", "property", "loan"]
    #   APPRAISAL        -> ["property"]
    #   INCOME_VERIFICATION -> ["borrower", "income"]
    #   OTHER            -> raise ValueError (this function should never be
    #                       called with OTHER; Exercise 2 short-circuits at
    #                       classify time)
    raise NotImplementedError("Exercise 1: implement _required_sections_for()")


__all__ = [
    "ToolDefinition",
    "classify_document",
    "doc_type_extractor",
    "extract_mortgage_data",
    "flag_for_review",
]
