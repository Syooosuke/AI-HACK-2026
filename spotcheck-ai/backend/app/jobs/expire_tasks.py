"""期限超過タスクのクローズ（docs/03-api.md 4節）。

APScheduler で5分ごとに実行し、起動直後にも1回実行する。

処理:
1. `deadline_at < now()` かつ `status IN ('open','in_progress','needs_info','screening')` を抽出
2. `approved_worker_count > 0` なら `completed`、そうでなければ `expired`
3. 未完了の assignment（`accepted` / `submitted`）を `expired` に更新

**物理削除は行わない。** 掲示板からの「削除」は status による絞り込みで表現する
（監査ログと合格済み取引を保全するため）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.db import get_session_factory
from app.core.logging import get_logger
from app.models import AssignmentStatus, TaskStatus
from app.repositories import assignment_repo, task_repo

logger = get_logger(__name__)


@dataclass
class ExpireSummary:
    expired: int = 0
    completed: int = 0
    assignments_expired: int = 0

    @property
    def total(self) -> int:
        return self.expired + self.completed


def expire_overdue_tasks(session: Session, *, now: datetime | None = None) -> ExpireSummary:
    """期限を過ぎたタスクをクローズする。"""
    moment = now or datetime.now(UTC)
    summary = ExpireSummary()

    for task in task_repo.find_expired(session, moment):
        for assignment in assignment_repo.list_unfinished_by_task(session, task.id):
            assignment.status = AssignmentStatus.EXPIRED
            assignment.completed_at = moment
            summary.assignments_expired += 1

        # 合格済みの提出が1件以上あれば、期限切れではなく完了として扱う
        if task.approved_worker_count > 0:
            task.status = TaskStatus.COMPLETED
            summary.completed += 1
        else:
            task.status = TaskStatus.EXPIRED
            summary.expired += 1

    session.flush()
    return summary


def run_once() -> ExpireSummary:
    """スケジューラから呼ばれる入口。独立したセッションで実行しコミットする。"""
    factory = get_session_factory()
    with factory() as session:
        try:
            summary = expire_overdue_tasks(session)
            session.commit()
        except Exception:
            session.rollback()
            logger.exception("期限切れタスクの処理に失敗しました")
            return ExpireSummary()

    if summary.total or summary.assignments_expired:
        logger.info(
            "期限切れタスクを処理しました",
            extra={
                "expired": summary.expired,
                "completed": summary.completed,
                "assignments_expired": summary.assignments_expired,
            },
        )
    return summary
