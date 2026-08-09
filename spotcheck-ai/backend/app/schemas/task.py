"""依頼（task）関連のスキーマ（docs/03-api.md 3.1〜3.5, 3.9）。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field

from app.models.enums import AssignmentStatus, TaskStatus
from app.schemas.common import CamelModel

TimelineStepStatus = Literal["done", "current", "pending"]


class ReferenceImage(CamelModel):
    id: uuid.UUID
    image_url: str
    sort_order: int


class ReviewChecks(CamelModel):
    """画面②のチェック項目4行。"""

    safety: Literal["pass", "fail"]
    validity: Literal["pass", "fail"]
    risk: Literal["pass", "fail"]
    duplication: Literal["pass", "fail"]


class ReviewResult(CamelModel):
    decision: Literal["approved", "needs_info", "rejected"]
    score: int
    checks: ReviewChecks
    missing_info: list[str] = Field(default_factory=list)
    rejection_reason: str | None = None


class TaskSummary(CamelModel):
    """依頼作成・再審査のレスポンスに含める依頼情報。"""

    id: uuid.UUID
    status: TaskStatus
    title: str
    review_score: int | None = None
    review_summary: str | None = None
    scheduled_at: datetime
    deadline_at: datetime
    reward_amount: int
    required_worker_count: int


class TaskReviewResponse(CamelModel):
    task: TaskSummary
    review: ReviewResult


class TaskResubmitRequest(CamelModel):
    """`POST /api/tasks/{taskId}/resubmit`。description のみ必須、他は差分更新。"""

    description: str = Field(min_length=10, max_length=1000)
    scheduled_at: datetime | None = None
    deadline_at: datetime | None = None
    reward_amount: int | None = Field(default=None, ge=100, le=100000)


class TaskListItem(CamelModel):
    id: uuid.UUID
    title: str
    status: TaskStatus
    reward_amount: int
    required_worker_count: int
    approved_worker_count: int
    accepted_worker_count: int
    scheduled_at: datetime
    deadline_at: datetime
    location_address: str | None = None
    created_at: datetime


class TaskListResponse(CamelModel):
    tasks: list[TaskListItem]


class TimelineStep(CamelModel):
    step: str
    label: str
    status: TimelineStepStatus
    at: datetime | None = None


class MyAssignment(CamelModel):
    id: uuid.UUID
    status: AssignmentStatus
    retake_count: int
    remaining_retakes: int
    latest_submission_id: uuid.UUID | None = None


class TaskDetail(CamelModel):
    id: uuid.UUID
    title: str
    description: str
    location_lat: float
    location_lng: float
    location_address: str | None = None
    scheduled_at: datetime
    deadline_at: datetime
    reward_amount: int
    required_worker_count: int
    approved_worker_count: int
    remaining_slots: int
    status: TaskStatus
    review_summary: str | None = None
    reference_images: list[ReferenceImage] = Field(default_factory=list)
    # client のみ
    timeline: list[TimelineStep] | None = None
    # worker のみ
    distance_km: float | None = None
    my_assignment: MyAssignment | None = None


class NearbyTask(CamelModel):
    id: uuid.UUID
    title: str
    reward_amount: int
    distance_km: float
    scheduled_at: datetime
    deadline_at: datetime
    location_lat: float
    location_lng: float
    remaining_slots: int
    required_worker_count: int


class NearbyTaskListResponse(CamelModel):
    tasks: list[NearbyTask]


class AssignmentDetail(CamelModel):
    id: uuid.UUID
    task_id: uuid.UUID
    status: AssignmentStatus
    retake_count: int
    remaining_retakes: int


class AcceptTaskResponse(CamelModel):
    assignment: AssignmentDetail


class MyAssignmentItem(CamelModel):
    id: uuid.UUID
    task_id: uuid.UUID
    title: str
    status: AssignmentStatus
    retake_count: int
    remaining_retakes: int
    reward_amount: int
    deadline_at: datetime
    location_lat: float
    location_lng: float
    latest_submission_id: uuid.UUID | None = None


class MyAssignmentListResponse(CamelModel):
    assignments: list[MyAssignmentItem]


class CancelTaskResponse(CamelModel):
    task: TaskSummary
