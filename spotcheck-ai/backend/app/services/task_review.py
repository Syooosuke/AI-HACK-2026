"""機能A: 依頼コンテキスト審査（docs/04-ai-pipeline.md 2節）。

**LLMの `decision` をそのまま信用せず、サーバー側でこのモジュールが最終決定する。**
Phase 1 では OrcaClient のスタブ応答を使う（プロンプトの実装は Phase 3）。
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models import Task, TaskStatus
from app.prompts.task_review import SYSTEM_PROMPT, build_user_prompt
from app.repositories import ai_invocation_repo
from app.schemas.ai import TaskReviewResult
from app.schemas.task import ReviewChecks, ReviewResult
from app.services.orca_client import OrcaClient

logger = get_logger(__name__)


@dataclass
class ReviewOutcome:
    task_status: TaskStatus
    review: ReviewResult


def decide(result: TaskReviewResult, *, score_threshold: int) -> str:
    """判定ロジック（docs/04-ai-pipeline.md 2.3）。

    `duplication` は表示のみに使い、判定には用いない。
    """
    if result.safety == "fail" or result.risk == "fail":
        return "rejected"
    if result.validity == "fail" or result.score < score_threshold:
        return "needs_info"
    return "approved"


DECISION_TO_STATUS = {
    "approved": TaskStatus.OPEN,
    "needs_info": TaskStatus.NEEDS_INFO,
    "rejected": TaskStatus.REJECTED,
}


async def review_task(session: Session, task: Task, orca: OrcaClient) -> ReviewOutcome:
    """依頼を審査し、tasks の審査結果カラムと status を更新する。"""
    settings = get_settings()
    has_reference_images = bool(task.reference_images)

    def recorder(**kwargs: object) -> None:
        ai_invocation_repo.create(session, **kwargs)  # type: ignore[arg-type]

    orca_result = await orca.complete_json(
        purpose="task_review",
        system_prompt=SYSTEM_PROMPT,
        user_prompt=build_user_prompt(task, has_reference_images=has_reference_images),
        response_schema=TaskReviewResult,
        # 参考画像があるときは vision ルーターへ切り替える（docs/04-ai-pipeline.md 2.1）
        tier="vision" if has_reference_images else "light",
        related_type="task",
        related_id=task.id,
        recorder=recorder,
    )
    result = orca_result.parsed
    assert isinstance(result, TaskReviewResult)

    decision = decide(result, score_threshold=settings.task_review_score_threshold)
    status = DECISION_TO_STATUS[decision]

    task.status = status
    task.review_score = result.score
    task.review_summary = result.summary
    task.review_feedback = {
        "decision": decision,
        "checks": {
            "safety": result.safety,
            "validity": result.validity,
            "risk": result.risk,
            "duplication": result.duplication,
        },
        "missingInfo": result.missing_info if decision == "needs_info" else [],
        "rejectionReason": result.rejection_reason if decision == "rejected" else None,
        "llmDecision": result.decision,
    }

    logger.info(
        "依頼審査が完了しました",
        extra={
            "task_id": str(task.id),
            "decision": decision,
            "score": result.score,
            "is_stub": orca_result.is_stub,
        },
    )

    return ReviewOutcome(
        task_status=status,
        review=ReviewResult(
            decision=decision,
            score=result.score,
            checks=ReviewChecks(
                safety=result.safety,
                validity=result.validity,
                risk=result.risk,
                duplication=result.duplication,
            ),
            missing_info=result.missing_info if decision == "needs_info" else [],
            rejection_reason=result.rejection_reason if decision == "rejected" else None,
        ),
    )
