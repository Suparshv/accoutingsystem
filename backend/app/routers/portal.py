"""Portal (contact-role) endpoints (SPEC.md §9 portal, §10.10, §12.3).

The partner filter in list_my_documents is the single most security-sensitive
line in this whole slice: it comes from current_user.partner_id — the
verified JWT — never from a query parameter or request body. §12.3 shows the
exact WRONG version this file must never become.

Paying a document is NOT a separate portal-only endpoint: the frontend's
PaymentDialog posts to the regular POST /payments and POST
/payments/{id}/confirm routes, which now accept the contact role with a
server-side ownership check (see routers/payments.py) — one payment flow,
reused everywhere a "Register Payment" button appears (§7.8).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends

from app.core.deps import require_role
from app.database import get_db
from app.models.purchase import VendorBill
from app.models.sales import CustomerInvoice
from app.models.user import User
from app.schemas.common import Page
from app.schemas.portal import PortalDocumentRow
from app.services import payments as payments_service

router = APIRouter(prefix="/portal", tags=["portal"])


@router.get("/my-documents", response_model=Page[PortalDocumentRow])
def list_my_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("contact")),
) -> Page[PortalDocumentRow]:
    """Invoices AND bills belonging to the CURRENT user's partner (§9: "the
    same shape as My Invoices/My Bills, filtered to current_user.partner_id").

    Wrapped in the same Page[] envelope every other list endpoint in the app
    returns (§9 list_envelope) — this one just never has more than a single
    page's worth of rows, so page/page_size are fixed rather than accepted
    as query params. Returning a bare array here (as this endpoint used to)
    is exactly the "no endpoint ever returns an unbounded array" case §9
    warns against, and it silently broke MyDocuments.tsx, which — like every
    other page in this app — reads `data.items`.

    Note what is absent from the signature: no partner_id parameter of any
    kind. The filter derives entirely from current_user.partner_id, so
    there is nothing for a client to override even if it tried (§12.3's
    "the parameter is ignored entirely" scenario is satisfied by there
    being no such parameter to read in the first place).
    """
    if current_user.partner_id is None:
        return Page[PortalDocumentRow](items=[], total=0, page=1, page_size=0)

    rows: list[PortalDocumentRow] = []

    invoices = db.execute(
        select(CustomerInvoice)
        .where(CustomerInvoice.customer_id == current_user.partner_id)
        .order_by(CustomerInvoice.invoice_date.desc())
    ).scalars()
    for invoice in invoices:
        summary = payments_service.invoice_payment_summary(db, invoice.id)
        rows.append(
            PortalDocumentRow(
                id=invoice.id,
                document_type="invoice",
                number=invoice.number,
                date=invoice.invoice_date,
                total_amount=invoice.total_amount,
                amount_due=summary.amount_due,
                payment_status=summary.payment_status,
                state=invoice.state,
            )
        )

    bills = db.execute(
        select(VendorBill)
        .where(VendorBill.vendor_id == current_user.partner_id)
        .order_by(VendorBill.bill_date.desc())
    ).scalars()
    for bill in bills:
        summary = payments_service.bill_payment_summary(db, bill)
        rows.append(
            PortalDocumentRow(
                id=bill.id,
                document_type="bill",
                number=bill.number,
                date=bill.bill_date,
                total_amount=bill.total_amount,
                amount_due=summary.amount_due,
                payment_status=summary.payment_status,
                state=bill.state,
            )
        )

    return Page[PortalDocumentRow](
        items=rows, total=len(rows), page=1, page_size=len(rows)
    )
