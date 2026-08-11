"""認証（ログインID＋パスワード）のスキーマ。"""

from __future__ import annotations

import uuid

from pydantic import Field, field_validator

from app.core.security import MAX_PASSWORD_BYTES
from app.schemas.common import CamelModel

#: ログインIDに使える文字（半角英数字・アンダースコア）。
LOGIN_ID_PATTERN = r"^[A-Za-z0-9_]+$"
LOGIN_ID_MIN_LENGTH = 3
LOGIN_ID_MAX_LENGTH = 32
PASSWORD_MIN_LENGTH = 8


class SignupRequest(CamelModel):
    login_id: str = Field(
        min_length=LOGIN_ID_MIN_LENGTH, max_length=LOGIN_ID_MAX_LENGTH, pattern=LOGIN_ID_PATTERN
    )
    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=MAX_PASSWORD_BYTES)
    display_name: str = Field(min_length=1, max_length=40)

    @field_validator("password")
    @classmethod
    def validate_password_bytes(cls, value: str) -> str:
        """bcrypt は72バイトを超える分を無視するため、バイト数でも上限を確認する。"""
        if len(value.encode("utf-8")) > MAX_PASSWORD_BYTES:
            raise ValueError(f"パスワードは{MAX_PASSWORD_BYTES}バイト以内で入力してください。")
        return value


class LoginRequest(CamelModel):
    login_id: str = Field(min_length=1, max_length=LOGIN_ID_MAX_LENGTH)
    password: str = Field(min_length=1)


class AuthUser(CamelModel):
    """ログイン中のユーザー情報。パスワード関連の値は絶対に含めない。"""

    id: uuid.UUID
    login_id: str
    display_name: str
    trust_score: float
    completed_task_count: int
    avatar_url: str | None = None


class AuthResponse(CamelModel):
    """ログイン／新規登録の応答。フロントは token を保持して Bearer で送る。"""

    token: str
    token_type: str = "Bearer"
    expires_in: int
    user: AuthUser


class MeResponse(CamelModel):
    user: AuthUser
