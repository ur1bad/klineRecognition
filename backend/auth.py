from __future__ import annotations

from typing import Any, Optional

from fastapi import Depends, Header, HTTPException, status

from backend.services.auth_service import AuthError, AuthService, ROLE_ADMIN


auth_service = AuthService()


def get_current_user(authorization: Optional[str] = Header(default=None)) -> dict[str, Any]:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请先登录后再访问系统功能。",
        )

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录状态无效，请重新登录。",
        )

    try:
        user = auth_service.get_user_from_token(token.strip())
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录状态无效，请重新登录。",
        )
    return user


def require_admin(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    if current_user.get("role") != ROLE_ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前账号没有管理员权限。")
    return current_user
