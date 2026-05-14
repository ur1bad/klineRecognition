from __future__ import annotations

from typing import Any, Optional

from backend.db.database import connection_scope


TABLE_NAME = "recognition_records"


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _apply_stock_code_filter(filters: list[str], params: list[Any], stock_code: Optional[str]) -> None:
    normalized = (stock_code or "").strip()
    if not normalized:
        return
    filters.append("stock_code LIKE ? ESCAPE '\\'")
    params.append(f"%{_escape_like(normalized)}%")


def insert_record(payload: dict[str, Any]) -> int:
    fields = [
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
    user_id: Optional[int] = None,
    stock_code: Optional[str] = None,
    predicted_label: Optional[str] = None,
) -> list[dict[str, Any]]:
    sql = f"SELECT * FROM {TABLE_NAME}"
    filters: list[str] = []
    params: list[Any] = []

    if user_id is not None:
        filters.append("user_id = ?")
        params.append(int(user_id))
    _apply_stock_code_filter(filters, params, stock_code)
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


def count_records(
    user_id: Optional[int] = None,
    stock_code: Optional[str] = None,
    predicted_label: Optional[str] = None,
) -> int:
    sql = f"SELECT COUNT(1) AS total FROM {TABLE_NAME}"
    filters: list[str] = []
    params: list[Any] = []

    if user_id is not None:
        filters.append("user_id = ?")
        params.append(int(user_id))
    _apply_stock_code_filter(filters, params, stock_code)
    if predicted_label:
        filters.append("predicted_label = ?")
        params.append(predicted_label)

    if filters:
        sql += " WHERE " + " AND ".join(filters)

    with connection_scope() as connection:
        row = connection.execute(sql, params).fetchone()
    return int(row["total"] if row else 0)


def get_record(record_id: int, user_id: Optional[int] = None) -> Optional[dict[str, Any]]:
    sql = f"SELECT * FROM {TABLE_NAME} WHERE id = ?"
    params: list[Any] = [record_id]
    if user_id is not None:
        sql += " AND user_id = ?"
        params.append(int(user_id))
    with connection_scope() as connection:
        row = connection.execute(sql, params).fetchone()
    return dict(row) if row else None


def delete_record(record_id: int, user_id: Optional[int] = None) -> bool:
    sql = f"DELETE FROM {TABLE_NAME} WHERE id = ?"
    params: list[Any] = [record_id]
    if user_id is not None:
        sql += " AND user_id = ?"
        params.append(int(user_id))
    with connection_scope() as connection:
        cursor = connection.execute(sql, params)
    return cursor.rowcount > 0
