from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
from datetime import datetime, timedelta
from typing import Any, Optional

from backend.config import get_config
from backend.db import user_repository
from backend.services.record_service import RecordService


ROLE_USER = "user"
ROLE_ADMIN = "admin"
VALID_ROLES = {ROLE_USER, ROLE_ADMIN}
PASSWORD_HASH_ALGORITHM = "pbkdf2_sha256"
PASSWORD_HASH_ITERATIONS = 180_000
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{3,32}$")


class AuthError(RuntimeError):
    """Raised for authentication and authorization failures."""


class AuthService:
    def __init__(self) -> None:
        self.config = get_config()

    def ensure_default_admin(self) -> None:
        if user_repository.count_users() > 0:
            return

        username = self.config.default_admin_username or "admin"
        password = self.config.default_admin_password or "admin123456"
        self.create_user(username=username, password=password, role=ROLE_ADMIN, is_active=True)

    def create_user(
        self,
        *,
        username: str,
        password: str,
        role: str = ROLE_USER,
        is_active: bool = True,
    ) -> dict[str, Any]:
        normalized_username = self._normalize_username(username)
        self._validate_username(normalized_username)
        self._validate_password(password)
        normalized_role = self._normalize_role(role)

        now = self._now()
        try:
            user_id = user_repository.create_user(
                {
                    "username": normalized_username,
                    "password_hash": self.hash_password(password),
                    "role": normalized_role,
                    "is_active": 1 if is_active else 0,
                    "created_at": now,
                    "updated_at": now,
                    "last_login_at": None,
                }
            )
        except Exception as exc:
            if user_repository.get_user_by_username(normalized_username):
                raise ValueError("用户名已存在。") from exc
            raise

        user = user_repository.get_user(user_id)
        if user is None:
            raise RuntimeError("用户创建成功，但回读失败。")
        return self.public_user(user)

    def register_user(self, username: str, password: str) -> dict[str, Any]:
        return self.create_user(username=username, password=password, role=ROLE_USER, is_active=True)

    def authenticate(self, username: str, password: str) -> Optional[dict[str, Any]]:
        user = user_repository.get_user_by_username(self._normalize_username(username))
        if user is None:
            return None
        if not int(user.get("is_active") or 0):
            raise AuthError("当前账号已被禁用，请联系管理员。")
        if not self.verify_password(password, str(user.get("password_hash") or "")):
            return None

        now = self._now()
        user_repository.update_last_login(int(user["id"]), now)
        refreshed = user_repository.get_user(int(user["id"])) or user
        return self.public_user(refreshed)

    def create_access_token(self, user: dict[str, Any]) -> str:
        now = datetime.now()
        expires_at = now + timedelta(minutes=max(1, int(self.config.auth_token_expire_minutes)))
        header = {"alg": "HS256", "typ": "JWT"}
        payload = {
            "sub": str(user["id"]),
            "username": str(user["username"]),
            "role": str(user["role"]),
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        }
        header_segment = self._b64encode_json(header)
        payload_segment = self._b64encode_json(payload)
        signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
        signature = self._sign(signing_input)
        return f"{header_segment}.{payload_segment}.{signature}"

    def get_user_from_token(self, token: str) -> Optional[dict[str, Any]]:
        payload = self._decode_token(token)
        user_id_text = str(payload.get("sub") or "").strip()
        if not user_id_text.isdigit():
            return None

        user = user_repository.get_user(int(user_id_text))
        if user is None or not int(user.get("is_active") or 0):
            return None
        return self.public_user(user)

    def list_users(self, *, limit: int = 200, offset: int = 0) -> dict[str, Any]:
        users = [self.public_user(user) for user in user_repository.list_users(limit=limit, offset=offset)]
        return {"total": user_repository.count_users(), "items": users}

    def update_user(
        self,
        *,
        user_id: int,
        role: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> Optional[dict[str, Any]]:
        payload: dict[str, Any] = {"updated_at": self._now()}
        if role is not None:
            payload["role"] = self._normalize_role(role)
        if is_active is not None:
            payload["is_active"] = 1 if is_active else 0
        user = user_repository.update_user(user_id, payload)
        return self.public_user(user) if user else None

    def reset_password(self, *, user_id: int, password: str) -> Optional[dict[str, Any]]:
        self._validate_password(password)
        user = user_repository.update_password(user_id, self.hash_password(password), self._now())
        return self.public_user(user) if user else None

    def delete_user(self, *, user_id: int) -> Optional[dict[str, Any]]:
        user = user_repository.get_user(user_id)
        if user is None:
            return None

        record_result = RecordService().delete_records_for_user(user_id)
        deleted = user_repository.delete_user(user_id)
        return {
            "user_id": int(user_id),
            "deleted": bool(deleted),
            **record_result,
        }

    def change_password(
        self,
        *,
        user_id: int,
        current_password: str,
        new_password: str,
    ) -> Optional[dict[str, Any]]:
        user = user_repository.get_user(user_id)
        if user is None:
            return None
        if not self.verify_password(current_password, str(user.get("password_hash") or "")):
            raise AuthError("当前密码不正确。")
        self._validate_password(new_password)
        updated_user = user_repository.update_password(user_id, self.hash_password(new_password), self._now())
        return self.public_user(updated_user) if updated_user else None

    def public_user(self, user: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": int(user["id"]),
            "username": str(user["username"]),
            "role": str(user.get("role") or ROLE_USER),
            "is_active": bool(user.get("is_active")),
            "created_at": str(user.get("created_at") or ""),
            "updated_at": str(user.get("updated_at") or ""),
            "last_login_at": user.get("last_login_at"),
            "record_count": int(user.get("record_count") or 0),
        }

    def hash_password(self, password: str) -> str:
        salt = secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            PASSWORD_HASH_ITERATIONS,
        )
        return (
            f"{PASSWORD_HASH_ALGORITHM}${PASSWORD_HASH_ITERATIONS}${salt}$"
            f"{base64.b64encode(digest).decode('ascii')}"
        )

    def verify_password(self, password: str, stored_hash: str) -> bool:
        try:
            algorithm, iterations_text, salt, encoded_digest = stored_hash.split("$", 3)
            iterations = int(iterations_text)
        except ValueError:
            return False
        if algorithm != PASSWORD_HASH_ALGORITHM:
            return False

        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            iterations,
        )
        expected = base64.b64decode(encoded_digest.encode("ascii"))
        return hmac.compare_digest(digest, expected)

    def _decode_token(self, token: str) -> dict[str, Any]:
        try:
            header_segment, payload_segment, signature_segment = token.split(".", 2)
        except ValueError as exc:
            raise AuthError("登录状态无效，请重新登录。") from exc

        signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
        expected_signature = self._sign(signing_input)
        if not hmac.compare_digest(signature_segment, expected_signature):
            raise AuthError("登录状态无效，请重新登录。")

        payload = self._b64decode_json(payload_segment)
        expires_at = int(payload.get("exp") or 0)
        if expires_at <= int(datetime.now().timestamp()):
            raise AuthError("登录已过期，请重新登录。")
        return payload

    def _sign(self, value: bytes) -> str:
        secret = self.config.auth_secret or "kline-system-local-auth-secret"
        digest = hmac.new(secret.encode("utf-8"), value, hashlib.sha256).digest()
        return self._b64encode_bytes(digest)

    def _b64encode_json(self, payload: dict[str, Any]) -> str:
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return self._b64encode_bytes(raw)

    def _b64encode_bytes(self, value: bytes) -> str:
        return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")

    def _b64decode_json(self, value: str) -> dict[str, Any]:
        padding = "=" * (-len(value) % 4)
        decoded = base64.urlsafe_b64decode((value + padding).encode("ascii"))
        payload = json.loads(decoded.decode("utf-8"))
        if not isinstance(payload, dict):
            raise AuthError("登录状态无效，请重新登录。")
        return payload

    def _normalize_username(self, username: str) -> str:
        return str(username or "").strip()

    def _validate_username(self, username: str) -> None:
        if not USERNAME_PATTERN.fullmatch(username):
            raise ValueError("用户名需为 3-32 位字母、数字或下划线。")

    def _validate_password(self, password: str) -> None:
        if len(str(password or "")) < 6:
            raise ValueError("密码长度不能少于 6 位。")

    def _normalize_role(self, role: str) -> str:
        normalized = str(role or ROLE_USER).strip().lower()
        if normalized not in VALID_ROLES:
            raise ValueError("用户角色不合法。")
        return normalized

    def _now(self) -> str:
        return datetime.now().isoformat(timespec="seconds")
