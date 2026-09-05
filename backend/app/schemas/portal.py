"""Portal document schema (SPEC.md §9 portal).

A unified view over a contact's own customer invoices AND vendor bills —
the mockup's "My Invoices" / "My Bills" screens both read this one shape,
discriminated by `document_type`.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from app.core.enums import DocumentState, PaymentStatus
from app.schemas.common import Money


class PortalDocumentRow(BaseModel):
    id: int
    document_type: str
    number: str
    date: date
    total_amount: Money
    amount_due: Money
    payment_status: PaymentStatus
    state: DocumentState
