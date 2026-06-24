"""Typed result objects returned by the extraction pipeline.

These are Pydantic models so they (a) validate input shape automatically when
constructed from a ``tool_use`` block's input dict, and (b) round-trip cleanly
to JSON via ``model_dump()`` / ``model_validate()`` — which is how recorded
fixtures stay deterministic.
"""
from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class DocumentType(StrEnum):
    LOAN_APPLICATION = "loan_application"
    APPRAISAL = "appraisal"
    INCOME_VERIFICATION = "income_verification"
    OTHER = "other"


class _BaseRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Borrower(_BaseRecord):
    full_name: str
    coborrower_name: str | None = None
    ssn_last4: str | None = None
    date_of_birth: str | None = None
    email: str | None = None
    phone: str | None = None


class Property(_BaseRecord):
    address: str
    property_type: str
    property_type_detail: str | None = None
    occupancy_type: str | None = None
    occupancy_type_detail: str | None = None
    year_built: int | None = None
    gross_living_area_sqft: int | None = None
    hoa_dues_monthly: float | None = None
    appraised_value: float | None = None


class Loan(_BaseRecord):
    amount: float
    term_months: int | None = None
    interest_rate: float | None = None
    loan_purpose: str | None = None
    loan_purpose_detail: str | None = None
    loan_program: str | None = None


class Income(_BaseRecord):
    base_monthly: float | None = None
    bonus_monthly: float | None = None
    bonus_ytd: float | None = None
    commission_monthly: float | None = None
    overtime_monthly: float | None = None
    other_monthly: float | None = None
    stated_monthly_total: float | None = None

    @property
    def calculated_monthly_total(self) -> float | None:
        """Sum of the per-component monthly fields, or ``None`` if none set.

        ``None`` (versus ``0.0``) distinguishes "the document stated no income
        components" from "the document stated all components are zero". The
        validator interprets the two cases differently.
        """
        # TODO: Return the sum of base_monthly, bonus_monthly,
        # commission_monthly, overtime_monthly, and other_monthly, ignoring any
        # that are None. If NO component is set (every field is None), return
        # None — NOT 0.0. The validator depends on that distinction: a
        # document that stated no income components must not be treated as
        # "stated zero", which would mask real bugs in the pipeline.
        #
        # Hint: build a list of the five component values, filter out None,
        # and return sum() of what's left OR None if the filtered list is empty.
        raise NotImplementedError("Exercise 4: implement Income.calculated_monthly_total")


class MortgageExtraction(_BaseRecord):
    """Structured result of extracting one mortgage document.

    Every top-level section is optional at the Python level because different
    document types carry different sections (an appraisal has no income; an
    income-verification document has no loan). Per-document-type extractors
    narrow the JSON Schema ``required`` list so the model knows which sections
    it must populate; this Pydantic model accepts whichever sections were
    asked for and validates their interior shape.
    """

    borrower: Borrower | None = None
    property: Property | None = None
    loan: Loan | None = None
    income: Income | None = None


class Classification(_BaseRecord):
    """Result of the classification pass."""

    document_type: DocumentType
    reason: str


class Discrepancy(_BaseRecord):
    """One arithmetic inconsistency surfaced by the validator."""

    field: str
    calculated: float
    stated: float
    delta: float


class ValidationReport(_BaseRecord):
    """Output of the mathematical-consistency validator."""

    consistent: bool
    discrepancies: list[Discrepancy] = []
