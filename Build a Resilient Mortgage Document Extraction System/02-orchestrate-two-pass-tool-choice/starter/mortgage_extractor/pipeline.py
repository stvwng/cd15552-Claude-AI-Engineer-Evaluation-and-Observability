"""Two-pass extraction pipeline: classify, then extract.

The classification pass uses ``tool_choice={"type":"tool","name":...}`` — the
model is forced to call the classifier and cannot return free text. The
extraction pass uses ``tool_choice={"type":"any"}`` against a small set of
doc-type-specific tools (a primary extractor plus a ``flag_for_review`` escape
hatch). ``"any"`` rather than ``"auto"`` because ``"auto"`` would permit a
conversational text fallback; ``"any"`` guarantees a ``tool_use`` block.

This pattern mirrors the Architect's Playbook "broad-then-pinpoint" exploration
recipe: classify the document first, then drill into the doc-type-specific
extractor with a fallback for unrecoverable cases.
"""
from __future__ import annotations

import logging

from anthropic.types import Message, ToolUseBlock

from mortgage_extractor import prompts
from mortgage_extractor.client import RecordingClient
from mortgage_extractor.config import DEFAULT_MAX_TOKENS, DEFAULT_MODEL
from mortgage_extractor.errors import (
    ExtractionError,
    FlaggedForReviewError,
    UnsupportedDocumentTypeError,
)
from mortgage_extractor.models import (
    Classification,
    DocumentType,
    MortgageExtraction,
)
from mortgage_extractor.tools import (
    ToolDefinition,
    classify_document,
    doc_type_extractor,
    flag_for_review,
)

log = logging.getLogger(__name__)

_FLAG_TOOL_NAME = "flag_for_review"


class Pipeline:
    """Two-pass classifier + extractor over the Anthropic Messages API."""

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        client: RecordingClient | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> None:
        self.model = model
        self.client = client or RecordingClient()
        self.max_tokens = max_tokens

    def run(self, document_text: str) -> MortgageExtraction:
        """Classify, then extract. Short-circuit on DocumentType.OTHER."""
        classification = self.classify_document(document_text)
        if classification.document_type is DocumentType.OTHER:
            raise UnsupportedDocumentTypeError(classification.reason)
        return self.extract(document_text, classification.document_type)

    def classify_document(self, document_text: str) -> Classification:
        """Pass 1: forced classifier call.

        Force the model to call the classifier tool exactly once via
        ``tool_choice={"type": "tool", "name": <classifier name>}``. This pass
        must produce a routing decision, not free text.
        """
        classifier = classify_document()
        response = self.client.call(
            model=self.model,
            max_tokens=self.max_tokens,
            system=prompts.classifier_system_prompt(),
            tools=[classifier],
            tool_choice={"type": "tool", "name": classifier["name"]},
            messages=[{"role": "user", "content": document_text}],
        )

        # Forced tool_choice guarantees this block exists, so a miss here means
        # the response shape changed — surface it rather than silently coping.
        block = _single_tool_use_block(response, expected_name=classifier["name"])
        log.info(
            "classify_document: model=%s in_tokens=%d out_tokens=%d result=%s",
            self.model,
            response.usage.input_tokens,
            response.usage.output_tokens,
            _input_field(block, "document_type"),
        )
        return Classification.model_validate(block.input)

    def extract(
        self,
        document_text: str,
        doc_type: DocumentType,
    ) -> MortgageExtraction:
        """Pass 2: tool_choice="any" extraction.

        Register the doc-type-specific extractor alongside ``flag_for_review``
        and let the model choose. ``"any"`` is what makes that choice
        meaningful — with a single tool registered, the API would behave the
        same as forced.
        """
        # run() short-circuits on OTHER, but extract() is public: guard here so
        # a caller who bypasses run() cannot ask for an extractor that
        # doc_type_extractor() refuses to build.
        if doc_type is DocumentType.OTHER:
            raise UnsupportedDocumentTypeError(
                "extract() called with DocumentType.OTHER; the classifier "
                "should have short-circuited before reaching extraction."
            )

        extractor = doc_type_extractor(doc_type)
        tools: list[ToolDefinition] = [extractor, flag_for_review()]
        response = self.client.call(
            model=self.model,
            max_tokens=self.max_tokens,
            system=prompts.extractor_system_prompt(doc_type),
            tools=tools,
            tool_choice={"type": "any"},  # must call a tool, but may pick either
            messages=[{"role": "user", "content": document_text}],
        )

        # No expected_name: under "any" the model may legitimately pick either
        # registered tool, and narrowing here would turn a valid flag_for_review
        # call into an ExtractionError instead of a FlaggedForReviewError.
        block = _single_tool_use_block(response)
        log.info(
            "extract: model=%s doc_type=%s in_tokens=%d out_tokens=%d tool=%s",
            self.model,
            doc_type.value,
            response.usage.input_tokens,
            response.usage.output_tokens,
            block.name,
        )

        if block.name == _FLAG_TOOL_NAME:
            raise FlaggedForReviewError(_input_field(block, "reason"))

        if block.name != extractor["name"]:
            raise ExtractionError(
                f"Unexpected tool call {block.name!r}; expected "
                f"{extractor['name']!r} or {_FLAG_TOOL_NAME!r}."
            )

        return MortgageExtraction.model_validate(block.input)


def _single_tool_use_block(
    response: Message,
    *,
    expected_name: str | None = None,
) -> ToolUseBlock:
    """Pull the one ToolUseBlock out of an Anthropic Message response.

    Structured output lives in the ``tool_use`` block, not in the assistant
    text. Walk ``response.content`` looking for ``ToolUseBlock`` entries; if
    ``expected_name`` is set, narrow to matching blocks.
    """
    tool_uses = [block for block in response.content if isinstance(block, ToolUseBlock)]
    if not tool_uses:
        raise ExtractionError(
            "Response contained no tool_use block; got content blocks "
            f"{[type(block).__name__ for block in response.content]!r}."
        )

    if expected_name is None:
        return tool_uses[0]

    for block in tool_uses:
        if block.name == expected_name:
            return block

    raise ExtractionError(
        f"Expected a tool_use block named {expected_name!r}; got "
        f"{[block.name for block in tool_uses]!r}."
    )


def _input_field(block: ToolUseBlock, field: str) -> str:
    """Read one string field out of a tool_use input.

    ``ToolUseBlock.input`` is typed as ``object`` because the API returns
    whatever the tool's schema allows, so narrow before subscripting.
    """
    if isinstance(block.input, dict):
        return str(block.input.get(field, ""))
    return ""
