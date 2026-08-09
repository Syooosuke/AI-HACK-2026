"""デモ用のユーザー解決（D-06）。

本認証へ差し替えるときは、このモジュールと `app/api/deps.py` のみを修正すれば済むようにする。
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import Forbidden, Unauthenticated
from app.models import User, UserRole
from app.repositories import user_repo

DEMO_USER_HEADER = "X-Demo-User-Id"


def resolve_demo_user(session: Session, raw_user_id: str | None) -> User:
    """`X-Demo-User-Id` ヘッダーからユーザーを特定する。

    ヘッダー欠落・不正なUUID・存在しないIDはいずれも 401 とする（docs/03-api.md 1.1）。
    """
    if not raw_user_id:
        raise Unauthenticated(
            f"{DEMO_USER_HEADER} ヘッダーが指定されていません。デモユーザーを選択してください。"
        )
    try:
        user_id = uuid.UUID(raw_user_id)
    except ValueError as exc:
        raise Unauthenticated("ユーザーIDの形式が正しくありません。") from exc

    user = user_repo.get(session, user_id)
    if user is None:
        raise Unauthenticated("指定されたユーザーが存在しません。")
    return user


def ensure_role(user: User, expected: UserRole) -> User:
    label = "クライアント" if expected is UserRole.CLIENT else "ワーカー"
    if user.role is not expected:
        raise Forbidden(f"この操作は{label}のみ実行できます。")
    return user
