from __future__ import annotations

from typing import Any, Optional

from backend.db.database import connection_scope


USERS_TABLE = "users"


def create_user(payload: dict[str, Any]) -> int:
    fields = [
        "username",
        "password_hash",
        "role",
        "is_active",
        "created_at",
        "updated_at",
        "last_login_at",
    ]
    values = [payload.get(field) for field in fields]
    placeholders = ", ".join("?" for _ in fields)
    columns = ", ".join(fields)
    sql = f"INSERT INTO {USERS_TABLE} ({columns}) VALUES ({placeholders})"

    with connection_scope() as connection:
        cursor = connection.execute(sql, values)
        return int(cursor.lastrowid)


def count_users() -> int:
    with connection_scope() as connection:
        row = connection.execute(f"SELECT COUNT(1) AS total FROM {USERS_TABLE}").fetchone()
    return int(row["total"] if row else 0)


def get_user(user_id: int) -> Optional[dict[str, Any]]:
    with connection_scope() as connection:
        row = connection.execute(
            f"""
            SELECT
                u.*,
                COUNT(r.id) AS record_count
            FROM {USERS_TABLE} u
            LEFT JOIN recognition_records r ON r.user_id = u.id
            WHERE u.id = ?
            GROUP BY u.id
            """,
            [int(user_id)],
        ).fetchone()
    return dict(row) if row else None


def get_user_by_username(username: str) -> Optional[dict[str, Any]]:
    with connection_scope() as connection:
        row = connection.execute(
            f"SELECT * FROM {USERS_TABLE} WHERE username = ?",
            [username],
        ).fetchone()
    return dict(row) if row else None


def list_users(limit: int = 200, offset: int = 0) -> list[dict[str, Any]]:
    with connection_scope() as connection:
        rows = connection.execute(
            f"""
            SELECT
                u.id,
                u.username,
                u.role,
                u.is_active,
                u.created_at,
                u.updated_at,
                u.last_login_at,
                COUNT(r.id) AS record_count
            FROM {USERS_TABLE} u
            LEFT JOIN recognition_records r ON r.user_id = u.id
            GROUP BY u.id
            ORDER BY u.id ASC
            LIMIT ? OFFSET ?
            """,
            [int(limit), int(offset)],
        ).fetchall()
    return [dict(row) for row in rows]


def update_user(user_id: int, payload: dict[str, Any]) -> Optional[dict[str, Any]]:
    allowed_fields = ["role", "is_active", "updated_at"]
    assignments: list[str] = []
    values: list[Any] = []
    for field in allowed_fields:
        if field in payload:
            assignments.append(f"{field} = ?")
            values.append(payload[field])

    if not assignments:
        return get_user(user_id)

    values.append(int(user_id))
    with connection_scope() as connection:
        cursor = connection.execute(
            f"UPDATE {USERS_TABLE} SET {', '.join(assignments)} WHERE id = ?",
            values,
        )
        if cursor.rowcount <= 0:
            return None
    return get_user(user_id)


def update_password(user_id: int, password_hash: str, updated_at: str) -> Optional[dict[str, Any]]:
    with connection_scope() as connection:
        cursor = connection.execute(
            f"UPDATE {USERS_TABLE} SET password_hash = ?, updated_at = ? WHERE id = ?",
            [password_hash, updated_at, int(user_id)],
        )
        if cursor.rowcount <= 0:
            return None
    return get_user(user_id)


def update_last_login(user_id: int, last_login_at: str) -> None:
    with connection_scope() as connection:
        connection.execute(
            f"UPDATE {USERS_TABLE} SET last_login_at = ? WHERE id = ?",
            [last_login_at, int(user_id)],
        )


def delete_user(user_id: int) -> bool:
    with connection_scope() as connection:
        cursor = connection.execute(
            f"DELETE FROM {USERS_TABLE} WHERE id = ?",
            [int(user_id)],
        )
    return cursor.rowcount > 0
