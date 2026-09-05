"""Pydantic schemas for accounts and journals (SPEC.md §7.4, §9)."""

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.enums import (
    AccountGroup,
    AccountType,
    JournalType,
    is_group_type_consistent,
)


class AccountBase(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=150)
    account_group: AccountGroup
    account_type: AccountType

    @model_validator(mode="after")
    def check_group_type_consistent(self) -> "AccountBase":
        """Second enforcement of ck_accounts_group_type_consistent.

        The database CHECK constraint is the last line of defence and its error
        is not user-presentable. Validating here too means the client gets a
        clean 422 naming the problem, and the constraint stays as the guarantee
        that nothing — not a script, not psql — can write an inconsistent row.
        Both layers read ACCOUNT_TYPES_BY_GROUP, so they cannot drift (P7).
        """
        if not is_group_type_consistent(self.account_group, self.account_type):
            raise ValueError(
                f"account_type '{self.account_type.value}' is not valid for "
                f"account_group '{self.account_group.value}'"
            )
        return self


class AccountCreate(AccountBase):
    pass


class AccountUpdate(AccountBase):
    pass


class AccountRead(AccountBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_archived: bool


class JournalCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    journal_type: JournalType
    default_account_id: int


class JournalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    journal_type: JournalType
    default_account_id: int
