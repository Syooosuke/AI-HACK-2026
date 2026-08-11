"""投稿カード（一覧に並べる1件分）の組み立て。

ホーム・さがす・ハート欄はいずれもこのモジュールを通す。
タグ（SOLD / NEW / HOT）の判定条件を1か所にまとめ、画面ごとにズレないようにする。
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.storage import StorageBackend
from app.models import Task, TaskStatus, User
from app.repositories import assignment_repo, like_repo
from app.schemas.task import NearbyTask, TaskBadge

logger = get_logger(__name__)

#: 取引が終了したとみなす status（左上に SOLD を出す）
SOLD_STATUSES = (TaskStatus.COMPLETED,)


def build_badges(task: Task, *, now: datetime | None = None) -> list[TaskBadge]:
    """投稿カードの左上に出すタグを決める。

    - sold: 取引終了（完了済み）
    - new: 作成から `NEW_TASK_HOURS` 以内
    - hot: 詳細の閲覧数が `HOT_VIEW_COUNT` 以上
    """
    settings = get_settings()
    current = now or datetime.now(UTC)
    badges: list[TaskBadge] = []

    if task.status in SOLD_STATUSES:
        badges.append("sold")
    elif task.created_at >= current - timedelta(hours=settings.new_task_hours):
        # 取引終了済みに NEW は出さない（古い募集に見えないようにする）
        badges.append("new")

    if task.view_count >= settings.hot_view_count:
        badges.append("hot")
    return badges


async def thumbnail_url(task: Task, storage: StorageBackend) -> tuple[str | None, str | None]:
    """サムネイルの配信URLと由来を返す。

    生成済みサムネイルが無い場合は参考画像の1枚目で代用する
    （生成はバックグラウンドで走るため、それを待たずに表示できるようにする）。
    """
    key = task.thumbnail_image_url
    source = task.thumbnail_source
    if key is None and task.reference_images:
        key = task.reference_images[0].image_url
        source = "reference"
    if key is None:
        return None, None

    try:
        url = await storage.create_signed_url(
            bucket=get_settings().storage_bucket_processed, key=key
        )
    except Exception:  # noqa: BLE001 - 画像が出ないだけで一覧は表示する
        logger.warning("サムネイルURLを発行できませんでした", extra={"task_id": str(task.id)})
        return None, source
    return url, source


async def build_cards(
    session: Session,
    *,
    viewer: User,
    tasks: list[Task],
    storage: StorageBackend,
    distances_km: dict[uuid.UUID, float] | None = None,
) -> list[NearbyTask]:
    """依頼の一覧を投稿カードへ変換する。並び順は渡された `tasks` の順を保つ。"""
    if not tasks:
        return []

    task_ids = [task.id for task in tasks]
    active_counts = assignment_repo.count_active_by_task(session, task_ids)
    liked_ids = like_repo.liked_task_ids(session, user_id=viewer.id, task_ids=task_ids)
    now = datetime.now(UTC)

    # 署名URLの発行はネットワークI/Oのため並行して行う
    thumbnails = await asyncio.gather(*(thumbnail_url(task, storage) for task in tasks))

    cards: list[NearbyTask] = []
    for task, (url, source) in zip(tasks, thumbnails, strict=True):
        remaining = max(0, task.required_worker_count - active_counts.get(task.id, 0))
        cards.append(
            NearbyTask(
                id=task.id,
                title=task.title,
                reward_amount=task.reward_amount,
                distance_km=(distances_km or {}).get(task.id),
                scheduled_at=task.scheduled_at,
                deadline_at=task.deadline_at,
                location_lat=task.location_lat,
                location_lng=task.location_lng,
                location_address=task.location_address,
                remaining_slots=remaining,
                required_worker_count=task.required_worker_count,
                status=task.status,
                created_at=task.created_at,
                thumbnail_url=url,
                thumbnail_source=source,
                badges=build_badges(task, now=now),
                like_count=task.like_count,
                is_liked=task.id in liked_ids,
                view_count=task.view_count,
                is_mine=task.client_id == viewer.id,
            )
        )
    return cards


__all__ = ["build_badges", "build_cards", "thumbnail_url"]
