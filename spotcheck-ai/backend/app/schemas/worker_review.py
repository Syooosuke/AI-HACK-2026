"""依頼者によるワーカー評価のスキーマ。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from app.schemas.common import CamelModel

WorkerReviewTag = Literal["as_requested", "clear_photo", "fast_response", "accurate_location"]


class WorkerReviewCreate(CamelModel):
    rating: int = Field(ge=1, le=5)
    tags: list[WorkerReviewTag] = Field(default_factory=list, max_length=4)
    comment: str | None = Field(default=None, max_length=500)

    @field_validator("tags")
    @classmethod
    def unique_tags(cls, value: list[WorkerReviewTag]) -> list[WorkerReviewTag]:
        if len(value) != len(set(value)):
            raise ValueError("評価タグは重複して指定できません。")
        return value

    @field_validator("comment")
    @classmethod
    def normalize_comment(cls, value: str | None) -> str | None:
        normalized = value.strip() if value else ""
        return normalized or None


class WorkerReviewResponse(CamelModel):
    id: uuid.UUID
    submission_id: uuid.UUID
    worker_id: uuid.UUID
    rating: int
    tags: list[WorkerReviewTag]
    comment: str | None = None
    created_at: datetime


class ReceivedWorkerReview(CamelModel):
    """ワーカー本人向け。依頼者を特定できる情報は含めない。"""

    id: uuid.UUID
    submission_id: uuid.UUID
    task_id: uuid.UUID
    task_title: str
    rating: int
    tags: list[WorkerReviewTag]
    comment: str | None = None
    created_at: datetime


class ReceivedWorkerReviewList(CamelModel):
    reviews: list[ReceivedWorkerReview]
    average_rating: float | None = None
    review_count: int
