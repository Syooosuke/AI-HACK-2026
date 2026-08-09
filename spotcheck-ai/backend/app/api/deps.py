"""FastAPI の依存関係（docs/03-api.md 1.1）。

本認証へ差し替える際は、ここと `app/core/security.py` だけを修正すれば済む構造にしている。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import DEMO_USER_HEADER, ensure_role, resolve_demo_user
from app.models import User, UserRole

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    session: DbSession,
    x_demo_user_id: Annotated[str | None, Header(alias=DEMO_USER_HEADER)] = None,
) -> User:
    return resolve_demo_user(session, x_demo_user_id)


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(role: UserRole) -> Callable[[User], User]:
    """指定ロール以外は 403 を返す依存関係を作る。"""

    def dependency(user: CurrentUser) -> User:
        return ensure_role(user, role)

    return dependency


ClientUser = Annotated[User, Depends(require_role(UserRole.CLIENT))]
WorkerUser = Annotated[User, Depends(require_role(UserRole.WORKER))]

__all__ = [
    "ClientUser",
    "CurrentUser",
    "DbSession",
    "WorkerUser",
    "get_current_user",
    "get_db",
    "require_role",
]
