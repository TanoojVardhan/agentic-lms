"""Database connection for the app's own records (quizzes, attempts, results).

Uses SQLAlchemy, so the same code runs on SQLite (default, a local file with
zero setup) or any PostgreSQL host: Supabase, Neon, or Google Cloud SQL
(Firebase SQL Connect). To switch, set APP_DB_URL in backend/.env, e.g.
    APP_DB_URL=postgresql+psycopg2://user:password@host:5432/dbname
Tables are created automatically on first use.

This is deliberately separate from DATABASE_URL, which still points at the
old Supabase project and is not used by any code.
"""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


def init_db(url: str | None = None) -> Engine:
    """Create the engine and tables. Called lazily; tests may pass their own URL."""
    global _engine, _SessionLocal
    url = url or settings.app_db_url
    if url.startswith("sqlite"):
        _engine = create_engine(url, connect_args={"check_same_thread": False})
    else:
        # Hosted Postgres (e.g. Supabase's pooler) limits connections on free
        # plans, so keep the pool small and drop stale connections.
        _engine = create_engine(
            url, pool_pre_ping=True, pool_size=5, max_overflow=5, pool_recycle=300
        )
    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)

    from app.db import models  # noqa: F401  (register tables on Base)

    Base.metadata.create_all(_engine)
    return _engine


def get_session() -> Session:
    if _SessionLocal is None:
        init_db()
    return _SessionLocal()
