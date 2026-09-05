"""Coordinator — deterministic control-flow over the source readers.

Runs each scoped reader, collects successful claims into shared memory, and hands
them to synthesis. Error propagation is local-recovery: a reader that fails
returns a `ReaderResult` with structured `FailureContext`; the coordinator
proceeds on the remaining sources and annotates the gap in the briefing rather
than aborting. Only successful claims are written to shared memory — failures are
recorded as coverage gaps, not vectorized.

This is intentionally a plain control-flow function, not an LLM-driven
orchestrator (multi-agent orchestration is a separate module).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .memory import SharedMemory
from .models import ReaderResult
from .readers import (
    LOGISTICS_EXCLUSIVE_METRICS,
    NewsExtractor,
    read_audit,
    read_logistics,
    read_news,
    read_quality,
)
from .synthesis import Briefing, build_briefing

# Metrics each source is the sole expected provider of (for gap attribution).
EXCLUSIVE_METRICS = {"logistics": LOGISTICS_EXCLUSIVE_METRICS}


@dataclass
class InvestigationResult:
    briefing: Briefing
    reader_results: list[ReaderResult]


def investigate(
    supplier: str,
    data_dir: str | Path,
    extractor: NewsExtractor,
    *,
    simulate_logistics_timeout: bool = False,
    logistics_fail_after: int = 5,
    memory: SharedMemory | None = None,
) -> InvestigationResult:
    """Run every source reader, then synthesise what survived into a briefing.

    A reader that fails contributes a coverage gap rather than aborting the run,
    so the briefing reports what could not be read alongside what could.
    """
    data_dir = Path(data_dir)

    # Each reader is scoped to its own file and signature, so they are called
    # individually rather than through a uniform loop.
    reader_results: list[ReaderResult] = [
        read_audit(data_dir / "audit.json"),
        read_logistics(
            data_dir / "logistics.csv",
            fail_after=logistics_fail_after if simulate_logistics_timeout else None,
        ),
        read_quality(data_dir / "quality.sqlite"),
    ]
    # Sorted so the claim order — and the resulting briefing — is deterministic.
    for article in sorted((data_dir / "news").glob("*.txt")):
        reader_results.append(read_news(article, extractor))

    # Partial results from a failed read are deliberately excluded: they are
    # evidence about the failure, not claims the briefing should rest on.
    claims = [c for r in reader_results if r.ok for c in r.claims]
    present = {c.metric_id for c in claims}

    unavailable: dict[str, str] = {}
    for result in reader_results:
        if result.ok:
            continue
        failure_type = result.error.failure_type if result.error else "unknown failure"
        for metric_id in EXCLUSIVE_METRICS.get(result.source, ()):
            # Another source may still cover the metric — only a metric nobody
            # reported is a real gap.
            if metric_id not in present:
                unavailable[metric_id] = f"{result.source} read failed ({failure_type})"

    if memory is not None:
        memory.add_claims(claims)
    briefing = build_briefing(
        supplier,
        claims,
        memory,
        unavailable=unavailable,
        unavailable_sources=_unavailable_sources(reader_results),
    )
    return InvestigationResult(briefing=briefing, reader_results=reader_results)


def _unavailable_sources(reader_results: list[ReaderResult]) -> list[str]:
    """Distinct sources that failed, in the order they were read."""
    unavailable_sources: list[str] = []
    for result in reader_results:
        if not result.ok and result.source not in unavailable_sources:
            unavailable_sources.append(result.source)
    return unavailable_sources
