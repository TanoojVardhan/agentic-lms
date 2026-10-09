"""Check that the app database (APP_DB_URL in backend/.env) is reachable.

Usage, from backend/:   python scripts/check_db.py

Creates the tables if they don't exist yet and prints what is stored.
Never prints your password.
"""
import re
import sys

sys.path.insert(0, ".")

from sqlalchemy import func, inspect, select, text  # noqa: E402

from app.config import settings  # noqa: E402

url = settings.app_db_url
print("Database:", re.sub(r"://([^:/@]+):[^@]*@", r"://\1:****@", url))

try:
    from app.db.database import get_session, init_db
    from app.db.models import Attempt, AttemptAnswer, Quiz

    engine = init_db()
    with engine.connect() as conn:
        if engine.dialect.name == "postgresql":
            print("Connected:", conn.execute(text("select version()")).scalar().split(",")[0])
        else:
            print("Connected: SQLite (local file)")
    print("Tables:", ", ".join(sorted(inspect(engine).get_table_names())))
    with get_session() as db:
        for model in (Quiz, Attempt, AttemptAnswer):
            print(f"  {model.__tablename__}: {db.scalar(select(func.count()).select_from(model))} rows")
    print("OK - the backend can use this database.")
except Exception as exc:  # explain the common failures in plain words
    msg = str(exc)
    print("\nFAILED:", msg.splitlines()[0][:300] if msg else type(exc).__name__)
    low = msg.lower()
    if "password authentication failed" in low:
        print("Hint: wrong username or password in APP_DB_URL. The Supabase pooler username "
              "looks like postgres.<project-ref>, not just postgres.")
    elif "could not translate host name" in low or "name or service not known" in low:
        print("Hint: the host name is wrong. Copy the Session pooler string from Supabase > Connect.")
    elif "timeout" in low or "timed out" in low or "unreachable" in low:
        print("Hint: cannot reach the server. Use the Session pooler host (IPv4), not db.<ref>.supabase.co "
              "(IPv6 only), check the project is not paused, and that your network allows port 5432.")
    elif "psycopg2" in low:
        print("Hint: run  pip install psycopg2-binary")
    elif "port" in low:
        print("Hint: a special character in the password breaks the URL. Use a letters+digits password.")
    sys.exit(1)
