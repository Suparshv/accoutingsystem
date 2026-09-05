"""Portal (contact-role) endpoints (SPEC.md §9 portal, §10.10, §12.3).

The partner filter in list_my_documents is the single most security-sensitive
line in this whole slice: it comes from current_user.partner_id — the
verified JWT — never from a query parameter or request body. §12.3 shows the
exact WRONG version this file must never become.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import require_role
from app.core.enums import PaymentStatus
from app.core.errors import AppError, NotFoundError
from app.database import get_db
from app.models.sales import CustomerInvoice
from app.models.user import User
from app.schemas.sales import CustomerInvoiceListRow
from app.services import sales as sales_service

router = APIRouter(prefix="/portal", tags=["portal"])


@router.get("/my-documents", response_model=list[CustomerInvoiceListRow])
def list_my_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("contact")),
) -> list[CustomerInvoiceListRow]:
    """Invoices belonging to the CURRENT user's partner (§10.10).

    Note what is absent from the signature: no partner_id parameter of any
    kind. The filter derives entirely from current_user.partner_id, which
    comes from the verified JWT — there is no client input to ignore because
    none is accepted (§12.3's "the parameter is ignored entirely" scenario
    is satisfied by there being no such parameter to read in the first
    place). Vendor bills will join in here once the purchase module lands
    (§9: "invoices and bills WHERE partner_id = current_user.partner_id").
    """
    if current_user.partner_id is None:
        return []

    invoices = db.execute(
        select(CustomerInvoice)
        .where(CustomerInvoice.customer_id == current_user.partner_id)
        .order_by(CustomerInvoice.created_at.desc())
    ).scalars()

    rows = []
    for invoice in invoices:
        amount_paid = Decimal("0.00")
        amount_due, status_value = sales_service.compute_payment_status(
            invoice.total_amount, amount_paid
        )
        rows.append(
            CustomerInvoiceListRow(
                id=invoice.id,
                number=invoice.number,
                customer_name=invoice.customer_name,
                invoice_date=invoice.invoice_date,
                due_date=invoice.due_date,
                total_amount=invoice.total_amount,
                amount_due=amount_due,
                payment_status=PaymentStatus(status_value),
                state=invoice.state,
            )
        )
    return rows


@router.post("/pay/{invoice_id}", status_code=501, response_model=None)
def pay_my_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("contact")),
) -> None:
    """NOT YET WIRED — deliberately.

    The ownership check below is real and matches §10.10 (a contact gets 403
    on someone else's invoice, checked before anything else). What is
    missing is the actual payment: creating and confirming a Payment row is
    services/payments.py's job, and this task is explicitly scoped to not
    touch that module or guess at its function signatures. Once it lands,
    this handler should call its create-and-confirm entry point and return
    200, not 501.
    """
    invoice = db.get(CustomerInvoice, invoice_id)
    if invoice is None:
        raise NotFoundError(f"Customer invoice {invoice_id} does not exist.")
    if invoice.customer_id != current_user.partner_id:
        raise AppError(
            403,
            "INSUFFICIENT_ROLE",
            "You do not have permission to pay this invoice.",
        )
    raise AppError(
        501,
        "NOT_IMPLEMENTED",
        "Payments are not available yet in this build — blocked on the "
        "payments module (services/payments.py), owned separately.",
    )
