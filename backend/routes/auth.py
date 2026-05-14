from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from backend.auth import get_current_user
from backend.schemas import AuthResponseSchema, ChangePasswordRequest, LoginRequest, RegisterRequest, UserSchema
from backend.services.auth_service import AuthError, AuthService


router = APIRouter(prefix="/auth", tags=["auth"])
auth_service = AuthService()


@router.post("/register", response_model=AuthResponseSchema)
async def register(payload: RegisterRequest) -> AuthResponseSchema:
    try:
        user = auth_service.register_user(payload.username, payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return AuthResponseSchema(
        access_token=auth_service.create_access_token(user),
        user=UserSchema(**user),
    )


@router.post("/login", response_model=AuthResponseSchema)
async def login(payload: LoginRequest) -> AuthResponseSchema:
    try:
        user = auth_service.authenticate(payload.username, payload.password)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误。",
        )

    return AuthResponseSchema(
        access_token=auth_service.create_access_token(user),
        user=UserSchema(**user),
    )


@router.get("/me", response_model=UserSchema)
async def me(current_user: dict = Depends(get_current_user)) -> UserSchema:
    return UserSchema(**current_user)


@router.post("/change_password", response_model=UserSchema)
async def change_password(
    payload: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user),
) -> UserSchema:
    try:
        user = auth_service.change_password(
            user_id=int(current_user["id"]),
            current_password=payload.current_password,
            new_password=payload.new_password,
        )
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在。")
    return UserSchema(**user)
