from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from backend.config import get_config


CREATE_USERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT,
    last_login_at TEXT
);
"""

CREATE_RECORDS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS recognition_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    stock_code TEXT,
    image_path TEXT NOT NULL,
    predicted_label TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0,
    reason TEXT,
    source_type TEXT NOT NULL,
    window_size INTEGER,
    start_date TEXT,
    end_date TEXT,
    inference_model TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
"""

REQUIRED_RECORD_COLUMNS = {
    "id",
    "user_id",
    "stock_code",
    "image_path",
    "predicted_label",
    "confidence",
    "reason",
    "source_type",
    "window_size",
    "start_date",
    "end_date",
    "inference_model",
    "created_at",
}


def get_connection() -> sqlite3.Connection:
    config = get_config()
    config.ensure_directories()
    connection = sqlite3.connect(str(config.database_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def connection_scope() -> Iterator[sqlite3.Connection]:
    connection = get_connection()
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def init_db() -> None:
    with connection_scope() as connection:
        connection.execute(CREATE_USERS_TABLE_SQL)
        _ensure_records_table(connection)


def _table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row["name"]) for row in rows}


def _ensure_records_table(connection: sqlite3.Connection) -> None:
    existing_columns = _table_columns(connection, "recognition_records")
    if existing_columns and not REQUIRED_RECORD_COLUMNS.issubset(existing_columns):
        connection.execute("DROP TABLE IF EXISTS recognition_records")
        existing_columns = set()

    if not existing_columns:
        connection.execute(CREATE_RECORDS_TABLE_SQL)
