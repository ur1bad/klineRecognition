from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.auth import require_admin
from backend.schemas import (
    AdminCreateUserRequest,
    AdminDeleteUserResponse,
    AdminResetPasswordRequest,
    AdminUpdateUserRequest,
    UserSchema,
    UsersListResponseSchema,
)
from backend.services.auth_service import AuthService, ROLE_ADMIN


router = APIRouter(prefix="/admin/users", tags=["users"])
auth_service = AuthService()


@router.get("", response_model=UsersListResponseSchema)
async def list_users(
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(require_admin),
) -> UsersListResponseSchema:
    result = auth_service.list_users(limit=limit, offset=offset)
    return UsersListResponseSchema(**result)


@router.post("", response_model=UserSchema)
async def create_user(
    payload: AdminCreateUserRequest,
    current_user: dict = Depends(require_admin),
) -> UserSchema:
    try:
        user = auth_service.create_user(
            username=payload.username,
            password=payload.password,
            role=payload.role,
            is_active=payload.is_active,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return UserSchema(**user)


@router.patch("/{user_id}", response_model=UserSchema)
async def update_user(
    user_id: int,
    payload: AdminUpdateUserRequest,
    current_user: dict = Depends(require_admin),
) -> UserSchema:
    if int(current_user["id"]) == int(user_id):
        if payload.is_active is False:
            raise HTTPException(status_code=400, detail="不能禁用当前登录的管理员账号。")
        if payload.role is not None and payload.role.strip().lower() != ROLE_ADMIN:
            raise HTTPException(status_code=400, detail="不能将当前登录的管理员账号降级。")

    try:
        user = auth_service.update_user(user_id=user_id, role=payload.role, is_active=payload.is_active)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在。")
    return UserSchema(**user)


@router.delete("/{user_id}", response_model=AdminDeleteUserResponse)
async def delete_user(
    user_id: int,
    current_user: dict = Depends(require_admin),
) -> AdminDeleteUserResponse:
    return _delete_user(user_id=user_id, current_user=current_user)


@router.post("/{user_id}/delete", response_model=AdminDeleteUserResponse)
async def delete_user_with_post(
    user_id: int,
    current_user: dict = Depends(require_admin),
) -> AdminDeleteUserResponse:
    return _delete_user(user_id=user_id, current_user=current_user)


def _delete_user(user_id: int, current_user: dict) -> AdminDeleteUserResponse:
    if int(current_user["id"]) == int(user_id):
        raise HTTPException(status_code=400, detail="不能删除当前登录的管理员账号。")

    result = auth_service.delete_user(user_id=user_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在。")
    if not result.get("deleted"):
        raise HTTPException(status_code=400, detail="用户删除失败。")
    return AdminDeleteUserResponse(**result)


@router.post("/{user_id}/reset_password", response_model=UserSchema)
async def reset_password(
    user_id: int,
    payload: AdminResetPasswordRequest,
    current_user: dict = Depends(require_admin),
) -> UserSchema:
    try:
        user = auth_service.reset_password(user_id=user_id, password=payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在。")
    return UserSchema(**user)
