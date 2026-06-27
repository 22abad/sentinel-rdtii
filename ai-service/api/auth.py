from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from auth import (
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    forgot_password,
    get_current_user,
    login,
    register,
    reset_password,
)

router = APIRouter()


class LoginRequestOut(BaseModel):
    email: str
    password: str


@router.post("/auth/register")
async def auth_register(req: RegisterRequest):
    return await register(req)


@router.post("/auth/login")
async def auth_login(req: LoginRequest):
    return await login(req)


@router.post("/auth/forgot-password")
async def auth_forgot_password(req: ForgotPasswordRequest):
    return await forgot_password(req)


@router.post("/auth/reset-password")
async def auth_reset_password(req: ResetPasswordRequest):
    return await reset_password(req)


@router.get("/auth/me")
async def auth_me(current_user: dict = Depends(get_current_user)):
    return current_user

