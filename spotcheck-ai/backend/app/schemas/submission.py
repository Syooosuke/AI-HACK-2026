"""提出（submission）関連のスキーマ（docs/03-api.md 3.6〜3.8）。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field

from app.models.enums import AssignmentStatus, TaskStatus, ValidationStatus
from app.schemas.common import CamelModel
from app.schemas.user import WorkerSummary
from app.schemas.worker_review import WorkerReviewResponse

#: `ai_feedback.issues[].code` に使える定義済みコード（docs/02-database.md 2.5）
IssueCode = Literal[
    "SUBJECT_MISSING",
    "TOO_DARK",
    "TOO_BLURRY",
    "ANGLE_MISMATCH",
    "TOO_FAR",
    "OBSTRUCTED",
    "LOCATION_MISMATCH",
    "TIMESTAMP_MISMATCH",
    "OTHER",
]


class Issue(CamelModel):
    code: IssueCode
    message: str


class SubmissionCreated(CamelModel):
    id: uuid.UUID
    attempt_no: int
    ai_validation_status: ValidationStatus


class SubmissionCreateResponse(CamelModel):
    submission: SubmissionCreated
    poll_url: str


class SubmissionChecks(CamelModel):
    """画面⑦のチェック4項目（docs/03-api.md 3.7）。"""

    framing_ok: bool
    subject_present: bool
    location_verified: bool
    privacy_masked: bool


class RetakeInfo(CamelModel):
    allowed: bool
    remaining: int


class SubmissionStatusResponse(CamelModel):
    id: uuid.UUID
    attempt_no: int
    ai_validation_status: ValidationStatus
    ai_score: int | None = None
    reality_score: int | None = None
    #: マスキング済み画像の署名URL。**原本URLは絶対に含めない**
    processed_image_url: str | None = None
    checks: SubmissionChecks
    issues: list[Issue] = Field(default_factory=list)
    retake: RetakeInfo
    assignment_status: AssignmentStatus
    worker_review: WorkerReviewResponse | None = None


class TaskResultItem(CamelModel):
    submission_id: uuid.UUID
    processed_image_url: str | None = None
    captured_at: datetime
    captured_lat: float
    captured_lng: float
    location_label: str | None = None
    reality_score: int | None = None
    ai_summary: str | None = None
    location_check: dict | None = None
    worker: WorkerSummary
    worker_review: WorkerReviewResponse | None = None


class TaskResultsResponse(CamelModel):
    task_id: uuid.UUID
    status: TaskStatus
    result_summary: str | None = None
    approved_count: int
    required_worker_count: int
    results: list[TaskResultItem]
