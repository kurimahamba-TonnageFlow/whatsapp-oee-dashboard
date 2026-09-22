"""
Manual live integration script (NOT a pytest test): opens a raw psycopg
connection to the live Supabase database and runs `SELECT NOW();` to
confirm connectivity and credentials. Read-only.

Never runs automatically - execute directly:
    python scripts/manual_integration/database_connection_check.py
after setting the required confirmation environment variable (see
_safety.require_live_confirmation). Importing this module has no side
effects (including loading .env or reading DATABASE_URL, only ever
done inside run()); all execution lives inside run(), called only
from the __main__ guard below.
"""

import os
from pathlib import Path
import sys

import psycopg
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from _safety import require_live_confirmation


def run():
    require_live_confirmation(
        "database_connection_check.py",
        "Read-only: opens a raw connection to the live Supabase database "
        "and runs SELECT NOW() to confirm connectivity and credentials.",
    )

    load_dotenv()

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL was not found in .env")

    try:
        with psycopg.connect(database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT NOW();")
                database_time = cursor.fetchone()

                print("TonnageFlow Pulse database connection successful.")
                print(f"Supabase database time: {database_time[0]}")

    except Exception as error:
        print("Database connection failed.")
        print(f"Error: {error}")


if __name__ == "__main__":
    run()
