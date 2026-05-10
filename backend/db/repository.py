from __future__ import annotations

from typing import Any, Optional

from backend.db.database import connection_scope


TABLE_NAME = "recognition_records"


def insert_record(payload: dict[str, Any]) -> int:
    fields = [
        "stock_code",
        "image_path",
        "predicted_label",
        "confidence",
        "reason",
        "source_type",
        "window_size",
        "start_date",
        "end_date",
        "backend_mode",
        "created_at",
    ]
    values = [payload.get(field) for field in fields]
    placeholders = ", ".join("?" for _ in fields)
    columns = ", ".join(fields)
    sql = f"INSERT INTO {TABLE_NAME} ({columns}) VALUES ({placeholders})"

    with connection_scope() as connection:
        cursor = connection.execute(sql, values)
        return int(cursor.lastrowid)


def list_records(
    limit: int = 50,
    offset: int = 0,
    stock_code: Optional[str] = None,
    predicted_label: Optional[str] = None,
) -> list[dict[str, Any]]:
    sql = f"SELECT * FROM {TABLE_NAME}"
    filters: list[str] = []
    params: list[Any] = []

    if stock_code:
        filters.append("stock_code = ?")
        params.append(stock_code)
    if predicted_label:
        filters.append("predicted_label = ?")
        params.append(predicted_label)

    if filters:
        sql += " WHERE " + " AND ".join(filters)
    sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    with connection_scope() as connection:
        rows = connection.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def count_records(stock_code: Optional[str] = None, predicted_label: Optional[str] = None) -> int:
    sql = f"SELECT COUNT(1) AS total FROM {TABLE_NAME}"
    filters: list[str] = []
    params: list[Any] = []

    if stock_code:
        filters.append("stock_code = ?")
        params.append(stock_code)
    if predicted_label:
        filters.append("predicted_label = ?")
        params.append(predicted_label)

    if filters:
        sql += " WHERE " + " AND ".join(filters)

    with connection_scope() as connection:
        row = connection.execute(sql, params).fetchone()
    return int(row["total"] if row else 0)


def get_record(record_id: int) -> Optional[dict[str, Any]]:
    sql = f"SELECT * FROM {TABLE_NAME} WHERE id = ?"
    with connection_scope() as connection:
        row = connection.execute(sql, [record_id]).fetchone()
    return dict(row) if row else None


def delete_record(record_id: int) -> bool:
    sql = f"DELETE FROM {TABLE_NAME} WHERE id = ?"
    with connection_scope() as connection:
        cursor = connection.execute(sql, [record_id])
    return cursor.rowcount > 0
