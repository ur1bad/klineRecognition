from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from backend.config import get_config


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS recognition_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code TEXT,
    image_path TEXT NOT NULL,
    predicted_label TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0,
    reason TEXT,
    source_type TEXT NOT NULL,
    window_size INTEGER,
    start_date TEXT,
    end_date TEXT,
    backend_mode TEXT,
    created_at TEXT NOT NULL
);
"""


def get_connection() -> sqlite3.Connection:
    config = get_config()
    config.ensure_directories()
    connection = sqlite3.connect(str(config.database_path))
    connection.row_factory = sqlite3.Row
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
        connection.execute(CREATE_TABLE_SQL)
