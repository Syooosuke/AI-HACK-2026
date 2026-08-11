"""公開プロフィール（docs/03-api.md 3.4.1）。

閲覧専用。ロールによる出し分けはせず、ログインしていれば誰でも誰のプロフィールも見られる。
公開してよい項目の判断は `app/services/user_service.py` に集約している。
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.user import PublicProfile
from app.services import user_service

router = APIRouter(prefix="/api/users", tags=["profiles"])


@router.get("/{user_id}/public", response_model=PublicProfile)
def get_public_profile(
    session: DbSession, viewer: CurrentUser, user_id: uuid.UUID
) -> PublicProfile:
    """閲覧専用の公開プロフィール。

    `viewer` は認証を要求するためだけに受け取る（未ログインには公開しない）。
    """
    return user_service.build_public_profile(session, user_id)
