"""Apply Nightingale PostgreSQL migrations once, in filename order.

Run with DATABASE_OWNER_URL set to a database-owner connection string.  This
script records applied migration filenames, so it is safe to run again after a
successful setup and will apply only newly added migrations.
"""
from __future__ import annotations

import os
from pathlib import Path

import psycopg


MIGRATIONS = sorted((Path(__file__).parent / "migrations").glob("*.sql"))


def main() -> None:
    database_url = os.environ.get("DATABASE_OWNER_URL")
    if not database_url:
        raise SystemExit(
            "DATABASE_OWNER_URL is required. See the cross-platform Quick Start in README.md."
        )

    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """CREATE TABLE IF NOT EXISTS nightingale_schema_migrations (
                filename text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now()
                )"""
            )
            cursor.execute("SELECT filename FROM nightingale_schema_migrations")
            applied = {row[0] for row in cursor.fetchall()}

            for migration in MIGRATIONS:
                if migration.name in applied:
                    continue
                print(f"Applying {migration.name}")
                cursor.execute(migration.read_text(encoding="utf-8"))
                cursor.execute(
                    "INSERT INTO nightingale_schema_migrations(filename) VALUES (%s)",
                    (migration.name,),
                )
    print("Database migrations are up to date.")


if __name__ == "__main__":
    main()
