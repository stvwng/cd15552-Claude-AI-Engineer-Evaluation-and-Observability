"""Source readers — adapters over differently-shaped evidence sources that all
converge on the same `Claim` representation.

- `read_audit`     : structured supplier-audit JSON
- `read_logistics` : semi-structured shipment CSV (metrics derived from rows)
- `read_quality`   : internal quality records in SQLite
- `read_news`      : unstructured prose, extracted via a `NewsExtractor`
                     (the Anthropic SDK at runtime, a recorded fixture in tests)

Readers return `ReaderResult` — errors are values, not exceptions — so a single
unreadable source never aborts the investigation.
"""
from __future__ import annotations

import csv
import json
import sqlite3
from datetime import date
from pathlib import Path
from typing import Protocol

from .models import Claim, FailureContext, ReaderResult

AUDIT = "supplier_audit"
LOGISTICS = "logistics"
QUALITY = "internal_quality"
NEWS = "industry_news"


def read_audit(path: str | Path) -> ReaderResult:
    """Parse the structured supplier audit JSON into Claims."""
    path = Path(path)
    # TODO: If the file does not exist, return a ReaderResult with ok=False and a
    #       FailureContext(failure_type="file_not_found", ...). This is an access
    #       failure, distinct from a readable-but-empty source.
    # TODO: Otherwise, load the JSON, parse report_date into a real date, and map
    #       each metric into a Claim with source=AUDIT and source_date=report_date.
    #       Return ReaderResult(source=AUDIT, ok=True, claims=claims).
    return ReaderResult(source=AUDIT, ok=True, claims=[])


def _logistics_claims(rows: list[dict[str, str]]) -> list[Claim]:
    # TODO: Derive the delivery metrics from the shipment rows:
    #       on_time_delivery_rate, average_lead_time_days, late_shipment_count.
    #       Use max(collection_date) across rows as the source_date. Return one
    #       Claim per metric with source=LOGISTICS and confidence around 0.85.
    return []


# Metrics only this source provides — used to report a coverage gap when it fails.
LOGISTICS_EXCLUSIVE_METRICS = ("late_shipment_count",)


def read_logistics(path: str | Path, *, fail_after: int | None = None) -> ReaderResult:
    """Derive delivery metrics from the semi-structured shipment CSV.

    `fail_after` simulates a source timeout after reading that many rows: the
    reader returns `ok=False` with a `FailureContext` carrying the partial
    results gathered before the failure — it does not raise.
    """
    path = Path(path)
    # TODO: Handle a missing file as an access failure (ok=False), as in read_audit.
    # TODO: Read the CSV rows. An empty file is a valid empty result (ok=True, []).
    # TODO (Exercise 3): If fail_after is set and there are more rows than that,
    #       simulate a timeout: compute partial claims from rows[:fail_after] and
    #       return ok=False with a FailureContext(failure_type="timeout",
    #       partial_results=partial, ...). Do not raise.
    # TODO: Otherwise return ReaderResult(source=LOGISTICS, ok=True,
    #       claims=_logistics_claims(rows)).
    return ReaderResult(source=LOGISTICS, ok=True, claims=[])


def read_quality(path: str | Path) -> ReaderResult:
    """Read internal quality records from SQLite."""
    path = Path(path)
    # TODO: Handle a missing file as an access failure (ok=False).
    # TODO: Open the SQLite db, SELECT from quality_metrics, and map each row into
    #       a Claim with source=QUALITY and source_date=date.fromisoformat(recorded_date).
    return ReaderResult(source=QUALITY, ok=True, claims=[])


class NewsExtractor(Protocol):
    """Extracts structured claim dicts from one article's prose.

    Implemented by `AnthropicNewsExtractor` (live SDK call) at runtime and by a
    recorded-fixture extractor in tests. Returns a list of raw claim dicts
    matching the `Claim` field names (plus `needs_identifier`/`candidates`).
    """

    def extract(self, article_text: str) -> list[dict[str, object]]: ...


def read_news(path: str | Path, extractor: NewsExtractor) -> ReaderResult:
    """Extract Claims from an unstructured news article via `extractor`.

    A readable article that yields no supplier-relevant claims returns
    `ok=True, claims=[]` (a valid empty result), distinct from a missing file
    (`ok=False`). When the extractor surfaces an ambiguous entity match, the
    resulting Claim carries `needs_identifier=True` and the candidate list —
    the reader does not pick one heuristically.
    """
    path = Path(path)
    # TODO: Handle a missing file as an access failure (ok=False).
    # TODO: Call extractor.extract(article_text) to get raw claim dicts, then map
    #       each into a Claim with source=NEWS and source_date parsed from the dict.
    #       Carry needs_identifier and candidates straight through from the dict —
    #       do NOT resolve an ambiguous match yourself.
    return ReaderResult(source=NEWS, ok=True, claims=[])
