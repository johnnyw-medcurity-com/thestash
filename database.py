import datetime
import os
import sqlite3
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).parent))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "expense.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    client_id INTEGER NOT NULL REFERENCES clients(id),
    purpose TEXT,
    start_date TEXT,
    end_date TEXT,
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_id INTEGER NOT NULL REFERENCES trips(id),
    date TEXT NOT NULL,
    category TEXT NOT NULL,
    vendor TEXT,
    amount REAL NOT NULL,
    notes TEXT,
    flagged INTEGER NOT NULL DEFAULT 0,
    receipt_filename TEXT,
    miles REAL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS report_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_id INTEGER NOT NULL REFERENCES trips(id),
    recipient_email TEXT,
    recipient_name TEXT,
    sent_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mileage_rates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    effective_date TEXT NOT NULL UNIQUE,
    rate REAL NOT NULL,
    created_at TEXT NOT NULL
);
"""


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db():
    conn = get_db()
    conn.executescript(SCHEMA)
    # Lightweight migration for columns added after a database already
    # exists in the wild (CREATE TABLE IF NOT EXISTS above won't add them).
    existing_cols = {row["name"] for row in conn.execute("PRAGMA table_info(expenses)")}
    if "miles" not in existing_cols:
        conn.execute("ALTER TABLE expenses ADD COLUMN miles REAL")
    if "mileage_rate" not in existing_cols:
        conn.execute("ALTER TABLE expenses ADD COLUMN mileage_rate REAL")
        # Existing mileage rows were all priced at the old fixed rate.
        conn.execute("UPDATE expenses SET mileage_rate = 0.725 WHERE miles IS NOT NULL")

    # Seed the rate-history table once from the previous hardcoded defaults,
    # so the switch to a DB-managed, user-editable history doesn't lose the
    # dates/rates already baked into existing mileage expenses.
    if conn.execute("SELECT COUNT(*) AS n FROM mileage_rates").fetchone()["n"] == 0:
        now = datetime.datetime.utcnow().isoformat()
        for effective_date, rate in (("2026-01-01", 0.725), ("2026-07-01", 0.76)):
            conn.execute(
                "INSERT INTO mileage_rates (effective_date, rate, created_at) VALUES (?, ?, ?)",
                (effective_date, rate, now),
            )

    conn.commit()
    conn.close()
