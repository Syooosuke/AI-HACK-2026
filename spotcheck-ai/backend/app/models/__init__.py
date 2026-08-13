"""SQLAlchemyモデルの集約。

Alembic の autogenerate はここで import されたモデルのみを検出するため、
新しいモデルを追加したら必ずこのファイルにも追記すること。
"""

from app.models.ai_invocation import AiInvocation
from app.models.base import Base
from app.models.enums import (
    ACTIVE_ASSIGNMENT_STATUSES,
    PUBLIC_TASK_STATUSES,
    AssignmentStatus,
    PaymentDirection,
    PaymentStatus,
    TaskStatus,
    ValidationStatus,
)
from app.models.payment import Payment
from app.models.saved_search import SavedSearch
from app.models.submission import Submission
from app.models.task import Task, TaskReferenceImage
from app.models.task_assignment import TaskAssignment
from app.models.task_like import TaskLike
from app.models.user import User
from app.models.worker_review import WorkerReview

__all__ = [
    "ACTIVE_ASSIGNMENT_STATUSES",
    "PUBLIC_TASK_STATUSES",
    "AiInvocation",
    "AssignmentStatus",
    "Base",
    "Payment",
    "PaymentDirection",
    "PaymentStatus",
    "SavedSearch",
    "Submission",
    "Task",
    "TaskAssignment",
    "TaskLike",
    "TaskReferenceImage",
    "TaskStatus",
    "User",
    "ValidationStatus",
    "WorkerReview",
]
