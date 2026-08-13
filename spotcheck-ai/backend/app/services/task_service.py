"""依頼（task）に関する業務ロジック（docs/03-api.md 3.1〜3.5, 3.9）。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import Conflict, Forbidden, NotFound, ValidationError
from app.core.geo import bounding_box, haversine_meters
from app.core.logging import get_logger
from app.core.storage import StorageBackend
from app.models import (
    AssignmentStatus,
    Task,
    TaskStatus,
    User,
)
from app.models.task import MAX_REFERENCE_IMAGES
from app.repositories import assignment_repo, like_repo, submission_repo, task_repo, user_repo
from app.schemas.task import (
    AssignmentDetail,
    MyAssignment,
    MyAssignmentItem,
    NearbyTask,
    ReferenceImage,
    TaskDetail,
    TaskDuplicateRequest,
    TaskListItem,
    TaskResubmitRequest,
    TaskReviewResponse,
    TaskSummary,
    TimelineStep,
)
from app.services import task_card, task_review, user_service
from app.services.orca_client import OrcaClient
from app.services.uploads import extension_for, read_and_validate_image

logger = get_logger(__name__)

#: 参考画像は「ワーカーに見せる」ため、原本バケットではなく配信用バケットへ置く。
#: 原本バケット（STORAGE_BUCKET_RAW）は提出画像の原本専用とし、外部へ出さない。
REFERENCE_IMAGE_PREFIX = "task-reference"

#: 依頼取消が可能な status（docs/03-api.md 3.9）
CANCELLABLE_STATUSES = (TaskStatus.SCREENING, TaskStatus.NEEDS_INFO, TaskStatus.OPEN)


@dataclass
class TaskCreateInput:
    title: str
    description: str
    location_lat: float
    location_lng: float
    location_address: str | None
    scheduled_at: datetime
    deadline_at: datetime
    reward_amount: int
    required_worker_count: int


# ----------------------------------------------------------------------
# 依頼作成・再審査
# ----------------------------------------------------------------------
async def create_task(
    session: Session,
    *,
    client: User,
    data: TaskCreateInput,
    reference_images: list[UploadFile],
    storage: StorageBackend,
    orca: OrcaClient,
) -> TaskReviewResponse:
    _validate_schedule(data.scheduled_at, data.deadline_at)
    if len(reference_images) > MAX_REFERENCE_IMAGES:
        raise ValidationError(
            f"参考画像は最大{MAX_REFERENCE_IMAGES}枚までです。",
            details={"field": "referenceImages", "count": len(reference_images)},
        )

    task = Task(
        client_id=client.id,
        title=data.title,
        description=data.description,
        location_lat=data.location_lat,
        location_lng=data.location_lng,
        location_address=data.location_address,
        scheduled_at=data.scheduled_at,
        deadline_at=data.deadline_at,
        reward_amount=data.reward_amount,
        required_worker_count=data.required_worker_count,
        status=TaskStatus.SCREENING,
    )
    task_repo.create(session, task)

    for index, upload in enumerate(reference_images):
        payload, content_type = await read_and_validate_image(upload, field="referenceImages")
        key = f"{REFERENCE_IMAGE_PREFIX}/{task.id}/{index}.{extension_for(content_type)}"
        await storage.upload(
            bucket=get_settings().storage_bucket_processed,
            key=key,
            data=payload,
            content_type=content_type,
        )
        task_repo.add_reference_image(session, task_id=task.id, image_url=key, sort_order=index)
    session.refresh(task)

    outcome = await task_review.review_task(session, task, orca, storage)
    return TaskReviewResponse(task=_to_summary(task), review=outcome.review)


async def resubmit_task(
    session: Session,
    *,
    client: User,
    task_id: uuid.UUID,
    payload: TaskResubmitRequest,
    orca: OrcaClient,
    storage: StorageBackend,
) -> TaskReviewResponse:
    task = _get_owned_task(session, task_id, client)
    if task.status is not TaskStatus.NEEDS_INFO:
        raise Conflict("情報補足待ちの依頼のみ再審査できます。", code="INVALID_STATE")

    task.description = payload.description
    if payload.scheduled_at is not None:
        task.scheduled_at = payload.scheduled_at
    if payload.reward_amount is not None:
        task.reward_amount = payload.reward_amount
    if payload.deadline_at is not None:
        task.deadline_at = payload.deadline_at
    _validate_schedule(task.scheduled_at, task.deadline_at, require_future=False)

    task.status = TaskStatus.SCREENING
    session.flush()

    outcome = await task_review.review_task(session, task, orca, storage)
    return TaskReviewResponse(task=_to_summary(task), review=outcome.review)


async def duplicate_task(
    session: Session,
    *,
    client: User,
    source_task_id: uuid.UUID,
    payload: TaskDuplicateRequest,
    storage: StorageBackend,
    orca: OrcaClient,
) -> TaskReviewResponse:
    """本人の過去依頼を日時だけ差し替え、独立した新規依頼として審査する。"""
    source = _get_owned_task(session, source_task_id, client)
    _validate_schedule(payload.scheduled_at, payload.deadline_at)

    duplicate = Task(
        client_id=client.id,
        title=source.title,
        description=source.description,
        location_lat=source.location_lat,
        location_lng=source.location_lng,
        location_address=source.location_address,
        scheduled_at=payload.scheduled_at,
        deadline_at=payload.deadline_at,
        reward_amount=source.reward_amount,
        required_worker_count=source.required_worker_count,
        status=TaskStatus.SCREENING,
    )
    task_repo.create(session, duplicate)

    # 参考画像は配信用ストレージ上の不変なオブジェクトなので、再アップロードせず参照を共有する。
    for reference in source.reference_images:
        task_repo.add_reference_image(
            session,
            task_id=duplicate.id,
            image_url=reference.image_url,
            sort_order=reference.sort_order,
        )
    session.refresh(duplicate)

    outcome = await task_review.review_task(session, duplicate, orca, storage)
    return TaskReviewResponse(task=_to_summary(duplicate), review=outcome.review)


# ----------------------------------------------------------------------
# 受注・取消
# ----------------------------------------------------------------------
def accept_task(session: Session, *, worker: User, task_id: uuid.UUID) -> AssignmentDetail:
    """受注（docs/03-api.md 3.5）。枠の超過を防ぐため tasks を行ロックして判定する。"""
    settings = get_settings()

    # 1. tasks をロック（このトランザクション内では他の accept が待たされる）
    task = task_repo.get_for_update(session, task_id)
    if task is None:
        raise NotFound("指定された依頼が見つかりません。", code="TASK_NOT_FOUND")

    # 2. 自分が出した依頼は受注できない（1アカウントで両方の役割を持つため明示的に弾く）
    if task.client_id == worker.id:
        raise Forbidden("自分が作成した依頼は受注できません。", code="CANNOT_ACCEPT_OWN_TASK")

    # 3. 期限・状態の確認
    if task.status not in (TaskStatus.OPEN, TaskStatus.IN_PROGRESS):
        raise Conflict("この依頼は現在受注できません。", code="INVALID_STATE")
    if task.deadline_at <= datetime.now(UTC):
        raise Conflict("この依頼は期限を過ぎています。", code="INVALID_STATE")

    # 4. 同一ワーカーの重複受注
    existing = assignment_repo.get_by_task_and_worker(session, task_id=task_id, worker_id=worker.id)
    if existing is not None:
        if existing.status in (AssignmentStatus.ACCEPTED, AssignmentStatus.SUBMITTED):
            raise Conflict("すでにこの依頼を受注しています。", code="ALREADY_ACCEPTED")
        raise Conflict("この依頼はすでに完了または失格となっています。", code="ALREADY_ACCEPTED")

    # 5. 空き枠の確認
    if assignment_repo.count_active(session, task_id) >= task.required_worker_count:
        raise Conflict("受注枠がすでに埋まっています。", code="TASK_FULL")

    # 6. 受注を作成し、依頼を進行中にする
    assignment = assignment_repo.create(session, task_id=task_id, worker_id=worker.id)
    task.status = TaskStatus.IN_PROGRESS
    session.flush()

    logger.info(
        "依頼を受注しました",
        extra={"task_id": str(task_id), "worker_id": str(worker.id)},
    )
    return AssignmentDetail(
        id=assignment.id,
        task_id=task_id,
        status=assignment.status,
        retake_count=assignment.retake_count,
        remaining_retakes=settings.max_retake_count - assignment.retake_count,
    )


def withdraw_assignment(session: Session, *, worker: User, task_id: uuid.UUID) -> AssignmentDetail:
    """未提出の受注を辞退し、占有していた募集枠を再開放する。"""
    task = task_repo.get_for_update(session, task_id)
    if task is None:
        raise NotFound("指定された依頼が見つかりません。", code="TASK_NOT_FOUND")

    assignment = assignment_repo.get_by_task_and_worker(
        session, task_id=task_id, worker_id=worker.id
    )
    if assignment is None:
        raise NotFound("この依頼の受注情報が見つかりません。", code="ASSIGNMENT_NOT_FOUND")
    if assignment.status is not AssignmentStatus.ACCEPTED:
        raise Conflict(
            "撮影を提出する前の依頼のみ辞退できます。",
            code="INVALID_STATE",
        )
    if submission_repo.latest_by_assignment(session, assignment.id) is not None:
        raise Conflict(
            "撮影を一度でも提出した依頼は辞退できません。",
            code="INVALID_STATE",
        )

    assignment.status = AssignmentStatus.CANCELLED
    assignment.completed_at = datetime.now(UTC)
    session.flush()
    reopen_if_slot_available(session, task)
    session.flush()

    logger.info(
        "ワーカーが受注を辞退しました",
        extra={"task_id": str(task_id), "worker_id": str(worker.id)},
    )
    return AssignmentDetail(
        id=assignment.id,
        task_id=task_id,
        status=assignment.status,
        retake_count=assignment.retake_count,
        remaining_retakes=get_settings().max_retake_count - assignment.retake_count,
    )


def cancel_task(session: Session, *, client: User, task_id: uuid.UUID) -> TaskSummary:
    """依頼取消（docs/03-api.md 3.9）。受注済みの場合は取消できない。"""
    task = _get_owned_task(session, task_id, client)
    if task.status not in CANCELLABLE_STATUSES:
        raise Conflict("受注済み・完了済みの依頼は取消できません。", code="INVALID_STATE")
    task.status = TaskStatus.CANCELLED
    session.flush()
    return _to_summary(task)


def reopen_if_slot_available(session: Session, task: Task) -> None:
    """受注者が0人になった依頼を期限内なら掲示板へ戻す（D-08 / docs/02-database.md 3.1）。"""
    if task.status is not TaskStatus.IN_PROGRESS:
        return
    if task.deadline_at <= datetime.now(UTC):
        return
    if assignment_repo.count_active(session, task.id) == 0:
        task.status = TaskStatus.OPEN
        logger.info("受注者がいなくなったため依頼を再公開しました", extra={"task_id": str(task.id)})


# ----------------------------------------------------------------------
# 参照系
# ----------------------------------------------------------------------
def list_client_tasks(session: Session, client: User) -> list[TaskListItem]:
    tasks = task_repo.list_by_client(session, client.id)
    active_counts = assignment_repo.count_active_by_task(session, [task.id for task in tasks])
    return [
        TaskListItem(
            id=task.id,
            title=task.title,
            status=task.status,
            reward_amount=task.reward_amount,
            required_worker_count=task.required_worker_count,
            approved_worker_count=task.approved_worker_count,
            accepted_worker_count=active_counts.get(task.id, 0),
            scheduled_at=task.scheduled_at,
            deadline_at=task.deadline_at,
            location_address=task.location_address,
            created_at=task.created_at,
        )
        for task in tasks
    ]


def _select_nearby(
    session: Session,
    *,
    viewer_id: uuid.UUID,
    lat: float,
    lng: float,
    radius_km: float,
    limit: int,
    sort: str,
) -> list[tuple[Task, float]]:
    """近傍の公開依頼を (依頼, 距離km) の並び済みリストで返す。

    自分が出した依頼は受注できないため除外する。
    """
    now = datetime.now(UTC)
    min_lat, max_lat, min_lng, max_lng = bounding_box(lat, lng, radius_km)
    candidates = task_repo.find_board_tasks_in_box(
        session,
        min_lat=min_lat,
        max_lat=max_lat,
        min_lng=min_lng,
        max_lng=max_lng,
        now=now,
    )
    active_counts = assignment_repo.count_active_by_task(session, [task.id for task in candidates])

    found: list[tuple[Task, float]] = []
    for task in candidates:
        if task.client_id == viewer_id:
            continue  # 自分の依頼は一覧に出さない
        remaining = task.required_worker_count - active_counts.get(task.id, 0)
        if remaining <= 0:
            continue  # 0枠の依頼は一覧に出さない（docs/05-frontend.md 画面④）
        distance_m = haversine_meters(lat, lng, task.location_lat, task.location_lng)
        if distance_m > radius_km * 1000:
            continue
        found.append((task, round(distance_m / 1000, 2)))

    sort_keys = {
        "distance": lambda item: item[1],
        "reward": lambda item: -item[0].reward_amount,
        "deadline": lambda item: item[0].deadline_at,
    }
    found.sort(key=sort_keys.get(sort, sort_keys["distance"]))
    return found[:limit]


async def find_nearby(
    session: Session,
    *,
    viewer: User,
    lat: float,
    lng: float,
    radius_km: float,
    limit: int,
    sort: str,
    storage: StorageBackend,
) -> list[NearbyTask]:
    """近傍の公開依頼を投稿カードとして返す（ホーム・さがす）。"""
    found = _select_nearby(
        session,
        viewer_id=viewer.id,
        lat=lat,
        lng=lng,
        radius_km=radius_km,
        limit=limit,
        sort=sort,
    )
    return await task_card.build_cards(
        session,
        viewer=viewer,
        tasks=[task for task, _ in found],
        storage=storage,
        distances_km={task.id: distance for task, distance in found},
    )


def count_nearby(
    session: Session,
    *,
    viewer_id: uuid.UUID,
    lat: float,
    lng: float,
    radius_km: float,
    sort: str = "distance",
    limit: int = 100,
) -> int:
    """保存した検索条件の「該当件数」表示用。カードは組み立てずに件数だけ数える。"""
    return len(
        _select_nearby(
            session,
            viewer_id=viewer_id,
            lat=lat,
            lng=lng,
            radius_km=radius_km,
            limit=limit,
            sort=sort,
        )
    )


async def build_task_detail(
    session: Session,
    *,
    task_id: uuid.UUID,
    user: User,
    storage: StorageBackend,
    lat: float | None = None,
    lng: float | None = None,
) -> TaskDetail:
    """依頼詳細。投稿をタップしたときに依頼主が入力した内容を一通り返す。"""
    task = task_repo.get(session, task_id)
    if task is None:
        raise NotFound("指定された依頼が見つかりません。", code="TASK_NOT_FOUND")

    # 依頼のオーナーか、それ以外（撮影する側）かで返す内容を変える（docs/03-api.md 3.4）
    is_owner = task.client_id == user.id

    # HOTタグの判定に使う閲覧数。自分の依頼を自分で開いた分は数えない
    if not is_owner:
        task.view_count = task_repo.increment_view_count(session, task.id)
        session.commit()
        session.refresh(task)

    settings = get_settings()
    active_count = assignment_repo.count_active(session, task.id)
    owner = user_repo.get(session, task.client_id)
    thumbnail_url, _ = await task_card.thumbnail_url(task, storage)
    reference_images = await _signed_reference_images(task, storage)

    detail = TaskDetail(
        id=task.id,
        title=task.title,
        description=task.description,
        location_lat=task.location_lat,
        location_lng=task.location_lng,
        location_address=task.location_address,
        scheduled_at=task.scheduled_at,
        deadline_at=task.deadline_at,
        reward_amount=task.reward_amount,
        required_worker_count=task.required_worker_count,
        approved_worker_count=task.approved_worker_count,
        remaining_slots=max(0, task.required_worker_count - active_count),
        status=task.status,
        review_summary=task.review_summary,
        reference_images=reference_images,
        created_at=task.created_at,
        # 依頼主。公開プロフィールへ遷移できるよう id と依頼者としての実績も含める
        # （docs/03-api.md 3.4.1）。自分の依頼を見た場合も同じ形で返す。
        owner=(user_service.build_task_owner(session, owner) if owner is not None else None),
        thumbnail_url=thumbnail_url,
        badges=task_card.build_badges(task),
        like_count=task.like_count,
        is_liked=like_repo.get(session, user_id=user.id, task_id=task.id) is not None,
        view_count=task.view_count,
        is_mine=is_owner,
    )

    if is_owner:
        detail.timeline = _build_timeline(session, task)
    else:
        # 撮影する側には他ワーカーの提出画像を返さない（docs/03-api.md 3.4）
        if lat is not None and lng is not None:
            detail.distance_km = round(
                haversine_meters(lat, lng, task.location_lat, task.location_lng) / 1000, 2
            )
        assignment = assignment_repo.get_by_task_and_worker(
            session, task_id=task.id, worker_id=user.id
        )
        if assignment is not None:
            latest = submission_repo.latest_by_assignment(session, assignment.id)
            detail.my_assignment = MyAssignment(
                id=assignment.id,
                status=assignment.status,
                retake_count=assignment.retake_count,
                remaining_retakes=max(0, settings.max_retake_count - assignment.retake_count),
                latest_submission_id=latest.id if latest else None,
            )
    return detail


async def _signed_reference_images(task: Task, storage: StorageBackend) -> list[ReferenceImage]:
    """参考画像を表示できる形（署名付きURL）にして返す。"""
    bucket = get_settings().storage_bucket_processed
    images: list[ReferenceImage] = []
    for image in task.reference_images:
        try:
            url = await storage.create_signed_url(bucket=bucket, key=image.image_url)
        except Exception:  # noqa: BLE001 - 画像が出ないだけで詳細は表示する
            logger.warning("参考画像URLを発行できませんでした", extra={"task_id": str(task.id)})
            continue
        images.append(ReferenceImage(id=image.id, image_url=url, sort_order=image.sort_order))
    return images


def list_my_assignments(session: Session, worker: User) -> list[MyAssignmentItem]:
    settings = get_settings()
    rows = assignment_repo.list_by_worker_with_task(session, worker.id)
    items: list[MyAssignmentItem] = []
    for assignment, task in rows:
        latest = submission_repo.latest_by_assignment(session, assignment.id)
        items.append(
            MyAssignmentItem(
                id=assignment.id,
                task_id=task.id,
                title=task.title,
                status=assignment.status,
                retake_count=assignment.retake_count,
                remaining_retakes=max(0, settings.max_retake_count - assignment.retake_count),
                reward_amount=task.reward_amount,
                deadline_at=task.deadline_at,
                location_lat=task.location_lat,
                location_lng=task.location_lng,
                latest_submission_id=latest.id if latest else None,
            )
        )
    return items


# ----------------------------------------------------------------------
# 内部ヘルパー
# ----------------------------------------------------------------------
def _validate_schedule(
    scheduled_at: datetime, deadline_at: datetime, *, require_future: bool = True
) -> None:
    now = datetime.now(UTC)
    if require_future and scheduled_at <= now:
        raise ValidationError(
            "撮影希望日時は現在時刻より後を指定してください。",
            details={"field": "scheduledAt"},
        )
    if deadline_at < scheduled_at:
        raise ValidationError(
            "提出期限は撮影希望日時以降を指定してください。",
            details={"field": "deadlineAt"},
        )


def _get_owned_task(session: Session, task_id: uuid.UUID, client: User) -> Task:
    task = task_repo.get(session, task_id)
    if task is None:
        raise NotFound("指定された依頼が見つかりません。", code="TASK_NOT_FOUND")
    if task.client_id != client.id:
        raise Forbidden("他のクライアントの依頼は操作できません。")
    return task


def _to_summary(task: Task) -> TaskSummary:
    return TaskSummary(
        id=task.id,
        status=task.status,
        title=task.title,
        description=task.description,
        location_lat=task.location_lat,
        location_lng=task.location_lng,
        location_address=task.location_address,
        review_score=task.review_score,
        review_summary=task.review_summary,
        scheduled_at=task.scheduled_at,
        deadline_at=task.deadline_at,
        reward_amount=task.reward_amount,
        required_worker_count=task.required_worker_count,
    )


def _build_timeline(session: Session, task: Task) -> list[TimelineStep]:
    """画面③の進行状況タイムライン（docs/03-api.md 3.4）。"""
    assignments = assignment_repo.list_by_task(session, task.id)
    submissions = [
        submission
        for assignment in assignments
        if (submission := submission_repo.latest_by_assignment(session, assignment.id))
    ]

    published_at = (
        task.created_at
        if task.status
        not in (
            TaskStatus.SCREENING,
            TaskStatus.REJECTED,
            TaskStatus.NEEDS_INFO,
        )
        else None
    )
    first_accepted_at = min((a.accepted_at for a in assignments), default=None)
    first_submitted_at = min((s.created_at for s in submissions), default=None)
    completed_at = task.updated_at if task.status is TaskStatus.COMPLETED else None

    raw_steps: list[tuple[str, str, datetime | None]] = [
        ("published", "依頼公開", published_at),
        ("accepted", "ワーカーが受注", first_accepted_at),
        # 受注済みで未提出のあいだ「現地調査中」を current にするため、提出時刻で done にする
        ("in_survey", "現地調査中", first_submitted_at),
        ("submitted", "結果提出", first_submitted_at),
        ("completed", "完了", completed_at),
    ]

    steps: list[TimelineStep] = []
    current_assigned = False
    for step, label, at in raw_steps:
        if at is not None:
            steps.append(TimelineStep(step=step, label=label, status="done", at=at))
        elif not current_assigned:
            steps.append(TimelineStep(step=step, label=label, status="current", at=None))
            current_assigned = True
        else:
            steps.append(TimelineStep(step=step, label=label, status="pending", at=None))
    return steps
