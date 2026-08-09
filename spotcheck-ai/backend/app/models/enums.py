"""DBのENUM定義（docs/02-database.md 1節）。

値は SQL の ENUM ラベルと1対1で対応させる。ラベルを変更するとマイグレーションが必要になるため、
勝手に変えないこと。
"""

from __future__ import annotations

import enum


class UserRole(str, enum.Enum):
    CLIENT = "client"
    WORKER = "worker"


class TaskStatus(str, enum.Enum):
    SCREENING = "screening"
    REJECTED = "rejected"
    NEEDS_INFO = "needs_info"
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class AssignmentStatus(str, enum.Enum):
    ACCEPTED = "accepted"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class ValidationStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    APPROVED = "approved"
    REJECTED = "rejected"
    ERROR = "error"


class PaymentDirection(str, enum.Enum):
    CHARGE = "charge"
    PAYOUT = "payout"


class PaymentStatus(str, enum.Enum):
    STUB_PENDING = "stub_pending"
    STUB_SUCCEEDED = "stub_succeeded"
    STUB_FAILED = "stub_failed"


#: 受注枠を使用中とみなす assignment のステータス（docs/02-database.md 2.4）。
#: failed / cancelled / expired は枠を占有しないため、自動的に他ワーカーへ再開放される（D-08）。
ACTIVE_ASSIGNMENT_STATUSES = (
    AssignmentStatus.ACCEPTED,
    AssignmentStatus.SUBMITTED,
    AssignmentStatus.APPROVED,
)
