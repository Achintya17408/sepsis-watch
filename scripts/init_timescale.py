"""
Script: scripts/init_timescale.py
Run this ONCE after `alembic upgrade head` to enable TimescaleDB
and convert the vitals table into a hypertable.

Usage:
    python scripts/init_timescale.py
"""
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

SYNC_URL = os.getenv("SYNC_DATABASE_URL")  # uses port 5433 (mapped from Docker)


def init():
    conn = psycopg2.connect(SYNC_URL)
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;")
    print("TimescaleDB extension enabled.")

    cur.execute(
        "SELECT create_hypertable('vital_readings', 'recorded_at', if_not_exists => TRUE);"
    )
    print("vital_readings converted to hypertable.")

    cur.close()
    conn.close()
    print("Done.")


if __name__ == "__main__":
    init()
