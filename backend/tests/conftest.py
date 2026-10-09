"""Shared test setup: every test run uses a throwaway SQLite database, never
the real backend/agentic_lms.db."""
import pytest

from app.db.database import init_db


@pytest.fixture(autouse=True, scope="session")
def _test_database(tmp_path_factory):
    init_db(f"sqlite:///{tmp_path_factory.mktemp('db') / 'test.db'}")
