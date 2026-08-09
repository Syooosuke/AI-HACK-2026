"""決済スタブ（D-03 / docs/02-database.md 2.6）。

**実決済は行わない。** 取引の記録のみを残す。
外部決済SDKの導入・カード番号や口座番号の保存は行わない。

検品合格時に、クライアントへの `charge` とワーカーへの `payout` を1件ずつ作成し、
即座に `stub_succeeded` にする（docs/04-ai-pipeline.md 6節 6-6）。
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models import Payment, PaymentDirection, PaymentStatus, Submission, Task

logger = get_logger(__name__)


def record_settlement(
    session: Session, *, task: Task, submission: Submission
) -> tuple[Payment, Payment]:
    """合格した提出に対する課金と支払いを記録する。"""
    now = datetime.now(UTC)
    charge = Payment(
        task_id=task.id,
        submission_id=submission.id,
        user_id=task.client_id,
        direction=PaymentDirection.CHARGE,
        amount=task.reward_amount,
        status=PaymentStatus.STUB_SUCCEEDED,
        processed_at=now,
    )
    payout = Payment(
        task_id=task.id,
        submission_id=submission.id,
        user_id=submission.worker_id,
        direction=PaymentDirection.PAYOUT,
        amount=task.reward_amount,
        status=PaymentStatus.STUB_SUCCEEDED,
        processed_at=now,
    )
    session.add_all([charge, payout])
    session.flush()

    logger.info(
        "決済を記録しました（スタブ）",
        extra={
            "task_id": str(task.id),
            "submission_id": str(submission.id),
            "amount": task.reward_amount,
        },
    )
    return charge, payout
