"""Create beeplan role and database on local PostgreSQL. Requires admin password."""

from __future__ import annotations

import os
import sys

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT


def main() -> None:
    password = os.environ.get("POSTGRES_PASSWORD") or os.environ.get("PGPASSWORD")
    if not password:
        print(
            "Set POSTGRES_PASSWORD (password of PostgreSQL user 'postgres'), then rerun:\n"
            '  $env:POSTGRES_PASSWORD = "your-postgres-password"\n'
            "  py -3 scripts/setup_local_db.py",
            file=sys.stderr,
        )
        sys.exit(1)

    host = os.environ.get("POSTGRES_HOST", "127.0.0.1")
    port = int(os.environ.get("POSTGRES_PORT", "5432"))
    admin_user = os.environ.get("POSTGRES_ADMIN_USER", "postgres")

    conn = psycopg2.connect(
        host=host,
        port=port,
        user=admin_user,
        password=password,
        dbname="postgres",
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()

    cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", ("beeplan",))
    if cur.fetchone() is None:
        cur.execute(
            sql.SQL("CREATE USER {} WITH PASSWORD %s").format(sql.Identifier("beeplan")),
            ("beeplan",),
        )
        print("Created role beeplan")
    else:
        cur.execute(
            sql.SQL("ALTER USER {} WITH PASSWORD %s").format(sql.Identifier("beeplan")),
            ("beeplan",),
        )
        print("Updated password for role beeplan")

    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", ("beeplan",))
    if cur.fetchone() is None:
        cur.execute(
            sql.SQL("CREATE DATABASE {} OWNER {}").format(
                sql.Identifier("beeplan"),
                sql.Identifier("beeplan"),
            )
        )
        print("Created database beeplan")
    else:
        print("Database beeplan already exists")

    cur.close()
    conn.close()
    print("Done. DATABASE_URL=postgresql+psycopg2://beeplan:beeplan@localhost:5432/beeplan")


if __name__ == "__main__":
    main()
