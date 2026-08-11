"""認証（新規登録・ログイン・トークンからのユーザー解決）の業務ロジック。"""

from __future__ import annotations

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import Conflict, Unauthenticated
from app.core.logging import get_logger
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.models import User
from app.repositories import user_repo
from app.schemas.auth import AuthResponse, AuthUser, LoginRequest, SignupRequest
from app.services import avatar_service

logger = get_logger(__name__)

#: 認証失敗時のメッセージ。IDの存在有無を推測させないため、原因を区別せず同じ文言を返す。
INVALID_CREDENTIALS_MESSAGE = "ログインIDまたはパスワードが正しくありません。"


def _to_auth_user(user: User) -> AuthUser:
    return AuthUser(
        id=user.id,
        login_id=user.login_id,
        display_name=user.display_name,
        trust_score=float(user.trust_score),
        completed_task_count=user.completed_task_count,
        avatar_url=avatar_service.public_url(user),
    )


def _issue(user: User) -> AuthResponse:
    settings = get_settings()
    return AuthResponse(
        token=create_access_token(user.id),
        expires_in=settings.jwt_expire_seconds,
        user=_to_auth_user(user),
    )


def signup(session: Session, payload: SignupRequest) -> AuthResponse:
    """新規登録。ログインIDが既に使われていれば 409 を返す。"""
    if user_repo.get_by_login_id(session, payload.login_id) is not None:
        raise Conflict("このログインIDは既に使われています。", code="LOGIN_ID_TAKEN")

    user = User(
        login_id=payload.login_id,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name,
    )
    try:
        user_repo.create(session, user)
        session.commit()
    except IntegrityError as exc:
        # 同じログインIDの同時登録に備える（一意制約が最終的な守り手）
        session.rollback()
        raise Conflict("このログインIDは既に使われています。", code="LOGIN_ID_TAKEN") from exc

    session.refresh(user)
    logger.info("ユーザーを登録しました", extra={"user_id": str(user.id)})
    return _issue(user)


def login(session: Session, payload: LoginRequest) -> AuthResponse:
    """ログイン。ID不在・パスワード不一致のどちらも同じ 401 を返す。"""
    user = user_repo.get_by_login_id(session, payload.login_id)
    if user is None or not verify_password(payload.password, user.password_hash):
        raise Unauthenticated(INVALID_CREDENTIALS_MESSAGE, code="INVALID_CREDENTIALS")
    logger.info("ログインしました", extra={"user_id": str(user.id)})
    return _issue(user)


def resolve_user_from_token(session: Session, token: str) -> User:
    """アクセストークンから現在のユーザーを解決する（`app/api/deps.py` から呼ぶ）。"""
    user_id: uuid.UUID = decode_access_token(token)
    user = user_repo.get(session, user_id)
    if user is None:
        # トークンは正しいが利用者が削除済み
        raise Unauthenticated("ユーザーが存在しません。もう一度ログインしてください。")
    return user


def to_auth_user(user: User) -> AuthUser:
    """`GET /api/auth/me` 用の変換。"""
    return _to_auth_user(user)
