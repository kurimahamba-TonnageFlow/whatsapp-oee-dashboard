import os

import psycopg
from dotenv import load_dotenv


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