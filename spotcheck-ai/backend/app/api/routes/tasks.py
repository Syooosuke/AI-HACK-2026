"""依頼系エンドポイント（docs/03-api.md 3.1〜3.5, 3.9）。

ルーター層はHTTPの入出力のみを担い、業務ロジックは services に置く（CLAUDE.md 5節）。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, Query, UploadFile, status

from app.api.deps import ClientUser, CurrentUser, DbSession, WorkerUser
from app.core.storage import get_storage
from app.schemas.submission import TaskResultsResponse
from app.schemas.task import (
    AcceptTaskResponse,
    CancelTaskResponse,
    MyAssignmentListResponse,
    NearbyTaskListResponse,
    TaskDetail,
    TaskListResponse,
    TaskResubmitRequest,
    TaskReviewResponse,
)
from app.services import submission_service, task_service
from app.services.orca_client import get_orca_client
from app.services.task_service import TaskCreateInput

router = APIRouter(prefix="/api", tags=["tasks"])


@router.post("/tasks", response_model=TaskReviewResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    session: DbSession,
    client: ClientUser,
    title: Annotated[str, Form(min_length=1, max_length=60)],
    description: Annotated[str, Form(min_length=10, max_length=1000)],
    location_lat: Annotated[float, Form(alias="locationLat", ge=-90, le=90)],
    location_lng: Annotated[float, Form(alias="locationLng", ge=-180, le=180)],
    scheduled_at: Annotated[datetime, Form(alias="scheduledAt")],
    deadline_at: Annotated[datetime, Form(alias="deadlineAt")],
    reward_amount: Annotated[int, Form(alias="rewardAmount", ge=100, le=100000)],
    required_worker_count: Annotated[int, Form(alias="requiredWorkerCount", ge=1, le=10)],
    location_address: Annotated[str | None, Form(alias="locationAddress")] = None,
    reference_images: Annotated[list[UploadFile] | None, File(alias="referenceImages")] = None,
) -> TaskReviewResponse:
    """依頼作成＋AI審査。審査は同期実行し、その結果をそのまま返す（画面①→②）。"""
    return await task_service.create_task(
        session,
        client=client,
        data=TaskCreateInput(
            title=title,
            description=description,
            location_lat=location_lat,
            location_lng=location_lng,
            location_address=location_address,
            scheduled_at=scheduled_at,
            deadline_at=deadline_at,
            reward_amount=reward_amount,
            required_worker_count=required_worker_count,
        ),
        reference_images=[f for f in (reference_images or []) if f.filename],
        storage=get_storage(),
        orca=get_orca_client(),
    )


@router.get("/tasks", response_model=TaskListResponse)
def list_tasks(session: DbSession, client: ClientUser) -> TaskListResponse:
    return TaskListResponse(tasks=task_service.list_client_tasks(session, client))


@router.get("/tasks/nearby", response_model=NearbyTaskListResponse)
def list_nearby_tasks(
    session: DbSession,
    worker: WorkerUser,
    lat: Annotated[float, Query(ge=-90, le=90)],
    lng: Annotated[float, Query(ge=-180, le=180)],
    radius_km: Annotated[float, Query(alias="radiusKm", ge=0.5, le=50)] = 5,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    sort: Annotated[Literal["distance", "reward", "deadline"], Query()] = "distance",
) -> NearbyTaskListResponse:
    """近傍の公開依頼一覧（画面④）。"""
    return NearbyTaskListResponse(
        tasks=task_service.find_nearby(
            session, lat=lat, lng=lng, radius_km=radius_km, limit=limit, sort=sort
        )
    )


@router.get("/assignments/mine", response_model=MyAssignmentListResponse)
def list_my_assignments(session: DbSession, worker: WorkerUser) -> MyAssignmentListResponse:
    return MyAssignmentListResponse(assignments=task_service.list_my_assignments(session, worker))


@router.get("/tasks/{task_id}", response_model=TaskDetail)
def get_task(
    session: DbSession,
    user: CurrentUser,
    task_id: uuid.UUID,
    lat: Annotated[float | None, Query(ge=-90, le=90)] = None,
    lng: Annotated[float | None, Query(ge=-180, le=180)] = None,
) -> TaskDetail:
    """依頼詳細。ロールによって返す内容を変える（docs/03-api.md 3.4）。"""
    return task_service.build_task_detail(session, task_id=task_id, user=user, lat=lat, lng=lng)


@router.post("/tasks/{task_id}/resubmit", response_model=TaskReviewResponse)
async def resubmit_task(
    session: DbSession,
    client: ClientUser,
    task_id: uuid.UUID,
    payload: TaskResubmitRequest,
) -> TaskReviewResponse:
    """補足情報を追記して再審査（画面②の needs_info からの再提出）。"""
    return await task_service.resubmit_task(
        session,
        client=client,
        task_id=task_id,
        payload=payload,
        orca=get_orca_client(),
        storage=get_storage(),
    )


@router.post(
    "/tasks/{task_id}/accept",
    response_model=AcceptTaskResponse,
    status_code=status.HTTP_201_CREATED,
)
def accept_task(session: DbSession, worker: WorkerUser, task_id: uuid.UUID) -> AcceptTaskResponse:
    """受注（画面⑤）。枠の超過は 409 TASK_FULL。"""
    return AcceptTaskResponse(
        assignment=task_service.accept_task(session, worker=worker, task_id=task_id)
    )


@router.post("/tasks/{task_id}/cancel", response_model=CancelTaskResponse)
def cancel_task(session: DbSession, client: ClientUser, task_id: uuid.UUID) -> CancelTaskResponse:
    return CancelTaskResponse(
        task=task_service.cancel_task(session, client=client, task_id=task_id)
    )


@router.get("/tasks/{task_id}/results", response_model=TaskResultsResponse)
async def get_task_results(
    session: DbSession, client: ClientUser, task_id: uuid.UUID
) -> TaskResultsResponse:
    """合格済み提出の一覧（画面⑨）。合格した順に随時追加される（D-07）。"""
    return await submission_service.get_task_results(
        session, client=client, task_id=task_id, storage=get_storage()
    )
