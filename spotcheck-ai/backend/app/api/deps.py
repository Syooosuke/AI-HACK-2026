"""FastAPI の依存関係（docs/03-api.md 1.1）。

認証は `Authorization: Bearer <JWT>` のみ。ロールによる出し分けは行わない
（1アカウントで「依頼する」「撮影する」の両方ができる）。
リソースごとの権限は、依頼のオーナーか受注者かをサービス層で判定する。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import extract_bearer_token
from app.models import User
from app.services import auth_service

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    session: DbSession,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> User:
    """Authorization ヘッダーのトークンからログイン中のユーザーを解決する。"""
    token = extract_bearer_token(authorization)
    return auth_service.resolve_user_from_token(session, token)


CurrentUser = Annotated[User, Depends(get_current_user)]

__all__ = [
    "CurrentUser",
    "DbSession",
    "get_current_user",
    "get_db",
]
