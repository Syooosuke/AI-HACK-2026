"""依頼（task）関連のスキーマ（docs/03-api.md 3.1〜3.5, 3.9）。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field

from app.models.enums import AssignmentStatus, TaskStatus
from app.schemas.common import CamelModel

TimelineStepStatus = Literal["done", "current", "pending"]

#: 投稿カードの左上に出すタグ。
#: sold=取引終了 / new=新着 / hot=よく見られている
TaskBadge = Literal["sold", "new", "hot"]


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
    description: str
    location_lat: float
    location_lng: float
    location_address: str | None = None
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


class TaskDuplicateRequest(CamelModel):
    """過去の依頼を日時だけ変更して再投稿する。"""

    scheduled_at: datetime
    deadline_at: datetime


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


class TaskOwner(CamelModel):
    """依頼主（投稿者）の表示用情報。

    `id` は公開プロフィール `/users/[userId]` への導線に使う（docs/03-api.md 3.4.1）。
    `published_task_count` / `completion_rate` は依頼者としての実績で、
    受注前に「どんな依頼者か」を判断できるようにするために出す。
    母数は公開された依頼のみで、却下・審査中の依頼は含めない。
    """

    id: uuid.UUID
    display_name: str
    #: 0〜100。画面ではゲージで表示する
    trust_score: float
    completed_task_count: int
    avatar_url: str | None = None
    published_task_count: int = 0
    #: completed / published。母数0なら null
    completion_rate: float | None = None


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
    created_at: datetime
    #: 依頼主。投稿をタップして詳細を見るときに誰の依頼か分かるようにする
    owner: TaskOwner | None = None
    thumbnail_url: str | None = None
    badges: list[TaskBadge] = Field(default_factory=list)
    like_count: int = 0
    is_liked: bool = False
    view_count: int = 0
    is_mine: bool = False
    # オーナーのみ
    timeline: list[TimelineStep] | None = None
    # 撮影する側のみ
    distance_km: float | None = None
    my_assignment: MyAssignment | None = None


class NearbyTask(CamelModel):
    """投稿一覧（ホーム・さがす・ハート欄）に並べる1件分。"""

    id: uuid.UUID
    title: str
    reward_amount: int
    #: 中心座標が分かる場合のみ入る（ハート欄では None）
    distance_km: float | None = None
    scheduled_at: datetime
    deadline_at: datetime
    location_lat: float
    location_lng: float
    location_address: str | None = None
    remaining_slots: int
    required_worker_count: int
    status: TaskStatus
    created_at: datetime
    #: 正方形サムネイルの配信URL。生成前・取得失敗時は None
    thumbnail_url: str | None = None
    #: reference（参考画像）/ generated（AI生成）/ streetview / placeholder
    thumbnail_source: str | None = None
    badges: list[TaskBadge] = Field(default_factory=list)
    like_count: int = 0
    is_liked: bool = False
    view_count: int = 0
    #: 自分が出した依頼か（ハート欄には自分の依頼が並ぶこともある）
    is_mine: bool = False


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


class WithdrawAssignmentResponse(CamelModel):
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
