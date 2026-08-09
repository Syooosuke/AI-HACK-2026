"""SQLAlchemyモデルの集約。

Alembic の autogenerate はここで import されたモデルのみを検出するため、
新しいモデルを追加したら必ずこのファイルにも追記すること。
"""

from app.models.ai_invocation import AiInvocation
from app.models.base import Base
from app.models.enums import (
    ACTIVE_ASSIGNMENT_STATUSES,
    AssignmentStatus,
    PaymentDirection,
    PaymentStatus,
    TaskStatus,
    UserRole,
    ValidationStatus,
)
from app.models.payment import Payment
from app.models.submission import Submission
from app.models.task import Task, TaskReferenceImage
from app.models.task_assignment import TaskAssignment
from app.models.user import User

__all__ = [
    "ACTIVE_ASSIGNMENT_STATUSES",
    "AiInvocation",
    "AssignmentStatus",
    "Base",
    "Payment",
    "PaymentDirection",
    "PaymentStatus",
    "Submission",
    "Task",
    "TaskAssignment",
    "TaskReferenceImage",
    "TaskStatus",
    "User",
    "UserRole",
    "ValidationStatus",
]
