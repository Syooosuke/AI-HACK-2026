"""認証エンドポイント（ログインID＋パスワード）。"""

from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.auth import AuthResponse, LoginRequest, MeResponse, SignupRequest
from app.services import auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def signup(session: DbSession, payload: SignupRequest) -> AuthResponse:
    """新規登録。登録と同時にログイン状態にする（トークンを返す）。"""
    return auth_service.signup(session, payload)


@router.post("/login", response_model=AuthResponse)
def login(session: DbSession, payload: LoginRequest) -> AuthResponse:
    return auth_service.login(session, payload)


@router.get("/me", response_model=MeResponse)
def get_me(user: CurrentUser) -> MeResponse:
    """トークンの有効性確認と、ログイン中ユーザーの取得を兼ねる。"""
    return MeResponse(user=auth_service.to_auth_user(user))
