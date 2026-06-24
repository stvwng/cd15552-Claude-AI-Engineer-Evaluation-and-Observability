"""Live news-claim extraction via the Anthropic SDK.

`read_news` accepts any `NewsExtractor`; in production this implementation calls
Claude with a structured-output contract to convert article prose into claim
dicts. Tests inject a recorded-fixture extractor instead, so the test suite runs
offline — but the recorded fixtures were themselves produced by this same
extraction task against real Claude.

The prompt states the goal and the output contract; it does not prescribe
step-by-step parsing. It names the target supplier so the model can flag — not
silently resolve — an ambiguous entity match.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

MODEL = "claude-opus-4-8"

_CLAIM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "claim": {"type": "string"},
                    "evidence": {"type": "string"},
                    "source_date": {"type": "string", "format": "date"},
                    "confidence": {"type": "number"},
                    "metric_id": {"type": "string"},
                    "needs_identifier": {"type": "boolean"},
                    "candidates": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "claim",
                    "evidence",
                    "source_date",
                    "confidence",
                    "metric_id",
                    "needs_identifier",
                    "candidates",
                ],
            },
        }
    },
    "required": ["claims"],
}


def _system_prompt(supplier: str) -> str:
    # TODO: Return a system prompt that names the target supplier, states the goal
    #   (extract supply-chain risk findings as a structured claim-source mapping),
    #   and states the output contract — not step-by-step parsing rules. It must
    #   instruct the model to return an empty list for an unrelated article, and to
    #   set needs_identifier=true with a candidate list (rather than guessing) when
    #   the supplier is named ambiguously.
    raise NotImplementedError


class AnthropicNewsExtractor:
    """Extracts claim dicts from article prose using the Anthropic SDK."""

    def __init__(self, supplier: str, client: Any | None = None) -> None:
        self.supplier = supplier
        if client is None:
            import anthropic  # imported lazily so tests need no SDK credentials

            client = anthropic.Anthropic()
        self._client: Any = client

    def extract(self, article_text: str) -> list[dict[str, object]]:
        # TODO: Call self._client.messages.create with model=MODEL, the system
        #   prompt from self._system_prompt_for(), and structured output via
        #   output_config={"format": {"type": "json_schema", "schema": _CLAIM_SCHEMA}}
        #   (no assistant prefill). Parse the JSON text block and return
        #   payload["claims"] as a list of dicts.
        raise NotImplementedError

    def _system_prompt_for(self) -> str:
        return _system_prompt(self.supplier)


class RecordedNewsExtractor:
    """Replays recorded extraction output keyed by article text.

    Lets the CLI run offline against the stored fixtures (themselves produced by
    `AnthropicNewsExtractor` against real Claude). Same interface as the live
    extractor, so `read_news` is agnostic to which one it gets.
    """

    def __init__(self, news_dir: str | Path, fixture_dir: str | Path) -> None:
        news_dir, fixture_dir = Path(news_dir), Path(fixture_dir)
        self._by_text: dict[str, list[dict[str, object]]] = {}
        for article in news_dir.glob("*.txt"):
            fixture = fixture_dir / f"{article.stem}.json"
            if fixture.exists():
                self._by_text[article.read_text().strip()] = json.loads(fixture.read_text())

    def extract(self, article_text: str) -> list[dict[str, object]]:
        return self._by_text.get(article_text.strip(), [])
