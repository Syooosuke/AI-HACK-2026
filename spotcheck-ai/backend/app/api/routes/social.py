"""いいね・保存した検索条件（ハート欄）のエンドポイント。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DbSession
from app.core.storage import get_storage
from app.schemas.social import (
    LikedTaskListResponse,
    LikeResponse,
    SavedSearchCreateRequest,
    SavedSearchListResponse,
    SavedSearchResponse,
)
from app.services import social_service

router = APIRouter(prefix="/api", tags=["social"])


# ----------------------------------------------------------------------
# いいね
# ----------------------------------------------------------------------
@router.post("/tasks/{task_id}/like", response_model=LikeResponse)
def like_task(session: DbSession, user: CurrentUser, task_id: uuid.UUID) -> LikeResponse:
    """投稿右上のハートをタップしたとき。二重タップでも結果は同じ。"""
    return social_service.like_task(session, user=user, task_id=task_id)


@router.delete("/tasks/{task_id}/like", response_model=LikeResponse)
def unlike_task(session: DbSession, user: CurrentUser, task_id: uuid.UUID) -> LikeResponse:
    return social_service.unlike_task(session, user=user, task_id=task_id)


@router.get("/likes", response_model=LikedTaskListResponse)
async def list_liked_tasks(session: DbSession, user: CurrentUser) -> LikedTaskListResponse:
    """ハート欄の上半分（いいねした投稿）。"""
    return await social_service.list_liked_tasks(session, user=user, storage=get_storage())


# ----------------------------------------------------------------------
# 保存した検索条件
# ----------------------------------------------------------------------
@router.get("/saved-searches", response_model=SavedSearchListResponse)
def list_saved_searches(session: DbSession, user: CurrentUser) -> SavedSearchListResponse:
    """ハート欄の下半分（保存した検索条件）。"""
    return SavedSearchListResponse(searches=social_service.list_saved_searches(session, user=user))


@router.post(
    "/saved-searches", response_model=SavedSearchResponse, status_code=status.HTTP_201_CREATED
)
def create_saved_search(
    session: DbSession, user: CurrentUser, payload: SavedSearchCreateRequest
) -> SavedSearchResponse:
    return SavedSearchResponse(
        search=social_service.create_saved_search(session, user=user, payload=payload)
    )


@router.delete("/saved-searches/{search_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_saved_search(session: DbSession, user: CurrentUser, search_id: uuid.UUID) -> None:
    social_service.delete_saved_search(session, user=user, search_id=search_id)
