"""Mathematical-consistency validator.

The extractor pulls two redundant values from any line-itemized total: the
``calculated`` sum (computed in Python from the per-component fields) and the
``stated`` total (extracted verbatim from the document). When the document is
internally consistent these agree; when they don't, the discrepancy is
surfaced for human review rather than silently corrected.

The default tolerance is one dollar — small enough to catch real arithmetic
errors, loose enough to absorb cent-level OCR rounding that upstream document
conversion sometimes introduces. Override per-call when a domain demands
zero-tolerance or a percentage-based threshold.
"""
from __future__ import annotations

from mortgage_extractor.config import DEFAULT_TOLERANCE_USD
from mortgage_extractor.models import (
    Discrepancy,
    MortgageExtraction,
    ValidationReport,
)


def validate(
    extraction: MortgageExtraction,
    *,
    tolerance: float = DEFAULT_TOLERANCE_USD,
) -> ValidationReport:
    """Return a consistency report for ``extraction``.

    The validator currently checks one line-itemized total: ``total_monthly_income``,
    comparing ``Income.calculated_monthly_total`` against
    ``Income.stated_monthly_total``. Additional checks would be added the same
    way (compute, compare against stated, emit a :class:`Discrepancy` on mismatch).
    """
    # TODO: Implement the consistency check.
    #   1. Start with an empty discrepancies list.
    #   2. If extraction.income is not None, pull:
    #        calculated = extraction.income.calculated_monthly_total
    #        stated     = extraction.income.stated_monthly_total
    #      Only compare when BOTH are not None (an absent component side and an
    #      absent stated total are different facts; you cannot diff them).
    #   3. Compute delta = round(calculated - stated, 2).
    #   4. If abs(delta) > tolerance, append a Discrepancy with:
    #        field="total_monthly_income",
    #        calculated=round(calculated, 2),
    #        stated=round(stated, 2),
    #        delta=delta,
    #   5. Return ValidationReport(consistent=not discrepancies, discrepancies=discrepancies).
    #
    # Friction note: the default $1.00 tolerance absorbs cent-level OCR
    # rounding. If you set it to 0.0 you will get false-positive discrepancies
    # on documents like "$4,500.00" vs "$4,499.99". See the README for details.
    raise NotImplementedError("Exercise 4: implement validate()")
