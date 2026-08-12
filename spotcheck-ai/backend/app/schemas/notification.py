"""お知らせ（画面下部タブ）のスキーマ。"""

from __future__ import annotations

import uuid
from datetime import datetime

from app.models.enums import NotificationType
from app.schemas.common import CamelModel


class NotificationItem(CamelModel):
    id: uuid.UUID
    type: NotificationType
    title: str
    body: str | None = None
    task_id: uuid.UUID | None = None
    submission_id: uuid.UUID | None = None
    read_at: datetime | None = None
    created_at: datetime


class NotificationListResponse(CamelModel):
    notifications: list[NotificationItem]


class UnreadCountResponse(CamelModel):
    count: int
