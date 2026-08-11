"""いいね・保存した検索条件（ハート欄）の業務ロジック。"""

from __future__ import annotations

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import Conflict, Forbidden, NotFound
from app.core.logging import get_logger
from app.core.storage import StorageBackend
from app.models import SavedSearch, Task, User
from app.models.saved_search import MAX_SAVED_SEARCHES
from app.repositories import like_repo, saved_search_repo, task_repo
from app.schemas.social import (
    LikedTaskListResponse,
    LikeResponse,
    SavedSearchCreateRequest,
    SavedSearchItem,
)
from app.services import task_card, task_service

logger = get_logger(__name__)


# ----------------------------------------------------------------------
# いいね
# ----------------------------------------------------------------------
def _get_likeable_task(session: Session, *, user: User, task_id: uuid.UUID) -> Task:
    task = task_repo.get(session, task_id)
    if task is None:
        raise NotFound("指定された依頼が見つかりません。", code="TASK_NOT_FOUND")
    if task.client_id == user.id:
        # 自分の依頼は受注できないため、いいねの対象にもしない
        raise Forbidden("自分が出した依頼にはいいねできません。", code="CANNOT_LIKE_OWN_TASK")
    return task


def like_task(session: Session, *, user: User, task_id: uuid.UUID) -> LikeResponse:
    """いいねを付ける。すでに押している場合も同じ結果を返す（冪等）。"""
    task = _get_likeable_task(session, user=user, task_id=task_id)

    if like_repo.get(session, user_id=user.id, task_id=task_id) is None:
        try:
            like_repo.add(session, user_id=user.id, task_id=task_id)
        except IntegrityError:
            # 二重タップの競合。すでに付いているので問題ない
            session.rollback()
        else:
            task.like_count = like_repo.count_for_task(session, task_id)
            session.commit()
            session.refresh(task)

    return LikeResponse(task_id=task_id, liked=True, like_count=task.like_count)


def unlike_task(session: Session, *, user: User, task_id: uuid.UUID) -> LikeResponse:
    """いいねを取り消す。押していない場合も同じ結果を返す（冪等）。"""
    task = task_repo.get(session, task_id)
    if task is None:
        raise NotFound("指定された依頼が見つかりません。", code="TASK_NOT_FOUND")

    if like_repo.remove(session, user_id=user.id, task_id=task_id):
        task.like_count = like_repo.count_for_task(session, task_id)
        session.commit()
        session.refresh(task)

    return LikeResponse(task_id=task_id, liked=False, like_count=task.like_count)


async def list_liked_tasks(
    session: Session, *, user: User, storage: StorageBackend
) -> LikedTaskListResponse:
    """ハート欄の上半分。いいねした投稿を新しい順に返す（取引終了済みも含める）。"""
    tasks = like_repo.list_liked_tasks(session, user.id)
    cards = await task_card.build_cards(session, viewer=user, tasks=tasks, storage=storage)
    return LikedTaskListResponse(tasks=cards)


# ----------------------------------------------------------------------
# 保存した検索条件
# ----------------------------------------------------------------------
def _to_item(search: SavedSearch) -> SavedSearchItem:
    return SavedSearchItem(
        id=search.id,
        label=search.label,
        center_lat=search.center_lat,
        center_lng=search.center_lng,
        location_address=search.location_address,
        radius_km=search.radius_km,
        sort=search.sort,
        last_match_count=search.last_match_count,
        created_at=search.created_at,
    )


def _default_label(payload: SavedSearchCreateRequest) -> str:
    """名前が未指定なら、住所か座標から自動で付ける。"""
    place = payload.location_address or (f"{payload.center_lat:.4f}, {payload.center_lng:.4f}")
    return f"{place} から{payload.radius_km:g}km"


def create_saved_search(
    session: Session, *, user: User, payload: SavedSearchCreateRequest
) -> SavedSearchItem:
    if saved_search_repo.count_by_user(session, user.id) >= MAX_SAVED_SEARCHES:
        raise Conflict(
            f"保存できる検索条件は{MAX_SAVED_SEARCHES}件までです。不要な条件を削除してください。",
            code="SAVED_SEARCH_LIMIT",
        )

    # 保存した時点の該当件数を控えておき、一覧に目安として出す
    match_count = task_service.count_nearby(
        session,
        viewer_id=user.id,
        lat=payload.center_lat,
        lng=payload.center_lng,
        radius_km=payload.radius_km,
        sort=payload.sort,
    )

    search = SavedSearch(
        user_id=user.id,
        label=(payload.label or "").strip() or _default_label(payload),
        center_lat=payload.center_lat,
        center_lng=payload.center_lng,
        location_address=payload.location_address,
        radius_km=payload.radius_km,
        sort=payload.sort,
        last_match_count=match_count,
    )
    saved_search_repo.create(session, search)
    session.commit()
    session.refresh(search)
    logger.info("検索条件を保存しました", extra={"user_id": str(user.id), "label": search.label})
    return _to_item(search)


def list_saved_searches(session: Session, *, user: User) -> list[SavedSearchItem]:
    """ハート欄の下半分。保存した検索条件を新しい順に返す。"""
    searches = saved_search_repo.list_by_user(session, user.id)
    items: list[SavedSearchItem] = []
    for search in searches:
        # 件数は開くたびに最新化する（保存後に増減するため）
        search.last_match_count = task_service.count_nearby(
            session,
            viewer_id=user.id,
            lat=search.center_lat,
            lng=search.center_lng,
            radius_km=search.radius_km,
            sort=search.sort,
        )
        items.append(_to_item(search))
    session.commit()
    return items


def delete_saved_search(session: Session, *, user: User, search_id: uuid.UUID) -> None:
    search = saved_search_repo.get(session, search_id)
    if search is None:
        raise NotFound("指定された検索条件が見つかりません。", code="SAVED_SEARCH_NOT_FOUND")
    if search.user_id != user.id:
        raise Forbidden("他のユーザーの検索条件は削除できません。")
    saved_search_repo.delete(session, search)
    session.commit()
