"""Partner (contact) CRUD — SPEC.md §9 masters, §10.3, §11."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_role
from app.core.enums import PartnerType
from app.core.errors import AppError
from app.core.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, paginate
from app.core.uploads import delete_image, save_image
from app.core.search import ilike_any, like_pattern
from app.database import get_db
from app.models.partner import Partner
from app.models.user import User
from app.schemas.common import Page
from app.schemas.partner import PartnerCreate, PartnerOut, PartnerUpdate

router = APIRouter(prefix="/partners", tags=["partners"])


def _get_active_partner(db: Session, partner_id: int) -> Partner:
    partner = db.get(Partner, partner_id)
    if partner is None or not partner.is_active:
        raise AppError(404, "NOT_FOUND", "Partner not found.")
    return partner


def _assert_email_available(
    db: Session, email: str | None, exclude_id: int | None = None
) -> None:
    if not email:
        return
    stmt = select(Partner).where(Partner.email == email)
    if exclude_id is not None:
        stmt = stmt.where(Partner.id != exclude_id)
    if db.execute(stmt).scalar_one_or_none() is not None:
        raise AppError(409, "EMAIL_TAKEN", "A contact with this email already exists.")


@router.get("", response_model=Page[PartnerOut])
def list_partners(
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    search: str | None = None,
    partner_type: PartnerType | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Page[PartnerOut]:
    stmt = select(Partner).where(Partner.is_active.is_(True))
    if search:
        stmt = stmt.where(
            ilike_any(like_pattern(search), Partner.name, Partner.email, Partner.phone)
        )
    if partner_type is not None:
        stmt = stmt.where(Partner.partner_type == partner_type)
    # id tiebreaker: created_at alone isn't unique (rows from one bulk
    # transaction share a timestamp), which lets LIMIT/OFFSET pagination
    # duplicate/skip rows across pages — see routers/sales_orders.py.
    stmt = stmt.order_by(Partner.created_at.desc(), Partner.id.desc())
    rows, total = paginate(db, stmt, page, page_size)
    return Page(items=rows, total=total, page=page, page_size=page_size)


@router.get("/{partner_id}", response_model=PartnerOut)
def get_partner(
    partner_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Partner:
    return _get_active_partner(db, partner_id)


@router.post("", response_model=PartnerOut, status_code=201)
def create_partner(
    body: PartnerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "accountant")),
) -> Partner:
    _assert_email_available(db, body.email)
    partner = Partner(**body.model_dump())
    db.add(partner)
    db.commit()
    db.refresh(partner)
    return partner


@router.put("/{partner_id}", response_model=PartnerOut)
def update_partner(
    partner_id: int,
    body: PartnerUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "accountant")),
) -> Partner:
    partner = _get_active_partner(db, partner_id)
    if body.email is not None:
        _assert_email_available(db, body.email, exclude_id=partner_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(partner, field, value)
    db.commit()
    db.refresh(partner)
    return partner


@router.delete("/{partner_id}", status_code=204, response_model=None)
def delete_partner(
    partner_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "accountant")),
) -> None:
    partner = _get_active_partner(db, partner_id)
    partner.is_active = False
    db.commit()


@router.post("/{partner_id}/image", response_model=PartnerOut)
def upload_partner_image(
    partner_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "accountant")),
) -> Partner:
    """Attach a profile image to a contact (SPEC.md §17 P1, image upload).

    Same roles as PUT /partners/{id} — this is an edit to the contact, and no
    weaker gate belongs on it just because the payload is a file.

    Written only after save_image has accepted the bytes, so a rejected upload
    leaves the previous image in place rather than clearing it. Replacing an
    image unlinks the old file once the new row is committed: doing it earlier
    would lose the old picture if the commit then failed.
    """
    partner = _get_active_partner(db, partner_id)
    previous = partner.image_path

    partner.image_path = save_image(file)
    db.commit()
    db.refresh(partner)

    if previous and previous != partner.image_path:
        delete_image(previous)
    return partner


@router.delete("/{partner_id}/image", response_model=PartnerOut)
def delete_partner_image(
    partner_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "accountant")),
) -> Partner:
    """Remove a contact's profile image (SPEC.md §17 P1, image upload).

    Returns 200 with the updated contact rather than 204, so the caller can
    render the cleared record straight from the response the way it does after
    an upload.

    Idempotent: clearing an image that is already absent is a success, not a
    404. The endpoint's job is to leave the contact without a picture, and it
    already is.
    """
    partner = _get_active_partner(db, partner_id)
    previous = partner.image_path

    partner.image_path = None
    db.commit()
    db.refresh(partner)

    # Unlinked only after the row is committed: the other order would delete
    # the file and then leave the column pointing at it if the commit failed.
    delete_image(previous)
    return partner
