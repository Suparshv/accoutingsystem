"""SQLAlchemy engine, session factory, declarative base and DB dependency."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    """Declarative base for every ORM model (SQLAlchemy 2.0 style)."""


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a session that is always closed.

    The caller owns the transaction boundary — commit happens in a service,
    never inside the posting engine (AGENTS.md R3).
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create every table declared on Base.

    There are no migrations by design (SPEC.md §3); the schema comes from
    create_all. Importing app.models first is what registers the mappers, so
    this picks up new models as they are added.
    """
    import app.models  # noqa: F401  — imported for its registration side effect

    Base.metadata.create_all(bind=engine)
