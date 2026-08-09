"""ユーザー系エンドポイント（docs/03-api.md 2節）。"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import DbSession
from app.repositories import user_repo
from app.schemas.user import DemoUser, DemoUserListResponse

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
