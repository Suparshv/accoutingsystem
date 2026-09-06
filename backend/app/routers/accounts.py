"""Chart of accounts HTTP layer (SPEC.md §9 accounting.accounts).

Routers parse, authorise, call, and shape. No business logic lives here.
"""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import require_role
from app.core.enums import AccountGroup, AccountType
from app.core.errors import NotFoundError
from app.core.search import ilike_any, like_pattern
from app.database import get_db
from app.models.account import Account
from app.models.user import User
from app.schemas.account import AccountCreate, AccountRead, AccountUpdate
from app.schemas.common import Page

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("", response_model=Page[AccountRead])
def list_accounts(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = None,
    account_type: AccountType | None = None,
    account_group: AccountGroup | None = None,
    include_archived: bool = False,
    current_user: User = Depends(require_role("admin", "accountant")),
) -> Page[AccountRead]:
    """Paginated chart of accounts. page_size is clamped at 100 (§10.11)."""
    stmt = select(Account)
    if not include_archived:
        stmt = stmt.where(Account.is_archived.is_(False))
    if account_type is not None:
        stmt = stmt.where(Account.account_type == account_type)
    if account_group is not None:
        stmt = stmt.where(Account.account_group == account_group)
    if search:
        stmt = stmt.where(ilike_any(like_pattern(search), Account.code, Account.name))

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()

    rows = db.execute(
        stmt.order_by(Account.code).offset((page - 1) * page_size).limit(page_size)
    ).scalars()

    return Page[AccountRead](
        items=[AccountRead.model_validate(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{account_id}", response_model=AccountRead)
def get_account(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "accountant")),
) -> AccountRead:
    return AccountRead.model_validate(_get_or_404(db, account_id))


@router.post("", response_model=AccountRead, status_code=status.HTTP_201_CREATED)
def create_account(
    payload: AccountCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "accountant")),
) -> AccountRead:
    """Group/type consistency is validated by the schema before we get here."""
    account = Account(**payload.model_dump())
    db.add(account)
    db.commit()
    db.refresh(account)
    return AccountRead.model_validate(account)


@router.put("/{account_id}", response_model=AccountRead)
def update_account(
    account_id: int,
    payload: AccountUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "accountant")),
) -> AccountRead:
    account = _get_or_404(db, account_id)
    for field, value in payload.model_dump().items():
        setattr(account, field, value)
    db.commit()
    db.refresh(account)
    return AccountRead.model_validate(account)


@router.post("/{account_id}/archive", response_model=AccountRead)
def archive_account(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "accountant")),
) -> AccountRead:
    """Archive, never delete — posted lines reference these rows (§7.4)."""
    account = _get_or_404(db, account_id)
    account.is_archived = True
    db.commit()
    db.refresh(account)
    return AccountRead.model_validate(account)


def _get_or_404(db: Session, account_id: int) -> Account:
    account = db.get(Account, account_id)
    if account is None:
        raise NotFoundError(f"Account {account_id} does not exist.")
    return account
