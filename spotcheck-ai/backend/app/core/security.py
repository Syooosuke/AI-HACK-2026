"""パスワードのハッシュ化とアクセストークン（JWT）の発行・検証。

このモジュールはDBに触らない。ユーザーの取得を伴う処理は `app/services/auth_service.py`、
リクエストからのユーザー解決は `app/api/deps.py` が担う。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.core.config import get_settings
from app.core.exceptions import Unauthenticated

#: Authorization ヘッダーのスキーム。
BEARER_PREFIX = "Bearer "
#: bcrypt が扱えるパスワードの最大バイト数（これを超える分は無視されるため入力側で弾く）。
MAX_PASSWORD_BYTES = 72
#: JWT の用途。他の目的のトークンと混用されないようにする。
TOKEN_TYPE = "access"


# ----------------------------------------------------------------------
# パスワード
# ----------------------------------------------------------------------
def hash_password(password: str) -> str:
    """パスワードを bcrypt でハッシュ化する。戻り値はDBへそのまま保存できる文字列。"""
    encoded = password.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        # スキーマ側でも弾いているが、ハッシュ化前に必ず確認する（黙って切り捨てさせない）
        raise ValueError(f"パスワードは{MAX_PASSWORD_BYTES}バイト以内である必要があります。")
    settings = get_settings()
    return bcrypt.hashpw(encoded, bcrypt.gensalt(rounds=settings.bcrypt_rounds)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """平文パスワードとハッシュを照合する。ハッシュが壊れている場合も False を返す。"""
    encoded = password.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        return False
    try:
        return bcrypt.checkpw(encoded, password_hash.encode("utf-8"))
    except ValueError:
        return False


# ----------------------------------------------------------------------
# アクセストークン
# ----------------------------------------------------------------------
def create_access_token(user_id: uuid.UUID, *, now: datetime | None = None) -> str:
    """ユーザーIDを主体（sub）に持つJWTを発行する。"""
    settings = get_settings()
    issued_at = now or datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "typ": TOKEN_TYPE,
        "iat": int(issued_at.timestamp()),
        "exp": int((issued_at + timedelta(days=settings.jwt_expire_days)).timestamp()),
    }
    return jwt.encode(payload, settings.effective_jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> uuid.UUID:
    """JWTを検証し、ユーザーIDを取り出す。不正・期限切れはいずれも 401 とする。"""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.effective_jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise Unauthenticated(
            "ログインの有効期限が切れました。もう一度ログインしてください。"
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise Unauthenticated("認証情報が正しくありません。もう一度ログインしてください。") from exc

    if payload.get("typ") != TOKEN_TYPE:
        raise Unauthenticated("認証情報が正しくありません。もう一度ログインしてください。")
    try:
        return uuid.UUID(str(payload["sub"]))
    except ValueError as exc:
        raise Unauthenticated("認証情報が正しくありません。もう一度ログインしてください。") from exc


def extract_bearer_token(authorization: str | None) -> str:
    """`Authorization: Bearer <token>` からトークン部分を取り出す。"""
    if not authorization:
        raise Unauthenticated("ログインが必要です。")
    if not authorization.startswith(BEARER_PREFIX):
        raise Unauthenticated("認証形式が正しくありません（Bearer トークンを指定してください）。")
    token = authorization[len(BEARER_PREFIX) :].strip()
    if not token:
        raise Unauthenticated("ログインが必要です。")
    return token
