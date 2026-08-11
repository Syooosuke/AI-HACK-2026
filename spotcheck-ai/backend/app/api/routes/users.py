"""ユーザー系エンドポイント（docs/03-api.md 2節）。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.repositories import user_repo
from app.schemas.user import DemoUser, DemoUserListResponse, PublicProfile
from app.services import user_service

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/demo", response_model=DemoUserListResponse)
def list_demo_users(session: DbSession) -> DemoUserListResponse:
    """デモユーザー一覧（画面切替用）。認証不要（この一覧から選んでIDを得るため）。"""
    users = user_repo.list_all(session)
    return DemoUserListResponse(
        users=[
            DemoUser(
                id=user.id,
                role=user.role,
                display_name=user.display_name,
                trust_score=float(user.trust_score),
                completed_task_count=user.completed_task_count,
                avatar_url=user.avatar_url,
            )
            for user in users
        ]
    )


@router.get("/{user_id}/public", response_model=PublicProfile)
def get_public_profile(
    session: DbSession, viewer: CurrentUser, user_id: uuid.UUID
) -> PublicProfile:
    """閲覧専用の公開プロフィール（docs/03-api.md 3.4.1）。

    ロールの制約はなく、誰でも誰のプロフィールも見られる。
    `viewer` は認証を要求するためだけに受け取る（未認証には公開しない）。
    """
    return user_service.build_public_profile(session, user_id)
