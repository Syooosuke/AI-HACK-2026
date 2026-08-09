"""機能A: 依頼コンテキスト審査（docs/04-ai-pipeline.md 2節）。

**LLMの `decision` をそのまま信用せず、サーバー側でこのモジュールが最終決定する。**
Phase 1 では OrcaClient のスタブ応答を使う（プロンプトの実装は Phase 3）。
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.storage import StorageBackend
from app.models import Task, TaskStatus
from app.models.task import MAX_REFERENCE_IMAGES
from app.prompts.task_review import SYSTEM_PROMPT, build_user_prompt
from app.repositories import ai_invocation_repo
from app.schemas.ai import TaskReviewResult
from app.schemas.task import ReviewChecks, ReviewResult
from app.services.orca_client import ImageInput, OrcaClient, encode_image_for_vlm

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


async def _load_reference_images(
    task: Task, storage: StorageBackend | None, *, skip: bool
) -> list[ImageInput]:
    """参考画像（最大3枚）を base64 にして返す。取得に失敗した画像はスキップする。"""
    if skip or storage is None or not task.reference_images:
        return []
    settings = get_settings()
    images: list[ImageInput] = []
    for reference in task.reference_images[:MAX_REFERENCE_IMAGES]:
        try:
            payload = await storage.download(
                bucket=settings.storage_bucket_processed, key=reference.image_url
            )
        except Exception:  # noqa: BLE001 - 参考画像が取れなくても審査自体は続行する
            logger.warning(
                "参考画像を取得できませんでした",
                extra={"task_id": str(task.id), "key": reference.image_url},
            )
            continue
        images.append(
            ImageInput(url=reference.image_url, base64_data=encode_image_for_vlm(payload))
        )
    return images


async def review_task(
    session: Session,
    task: Task,
    orca: OrcaClient,
    storage: StorageBackend | None = None,
) -> ReviewOutcome:
    """依頼を審査し、tasks の審査結果カラムと status を更新する。"""
    settings = get_settings()
    has_reference_images = bool(task.reference_images)
    # スタブモードでは画像を送らないため、無駄なダウンロードを避ける
    images = await _load_reference_images(task, storage, skip=orca.is_stub)

    orca_result = await orca.complete_json(
        purpose="task_review",
        system_prompt=SYSTEM_PROMPT,
        user_prompt=build_user_prompt(task, has_reference_images=has_reference_images),
        response_schema=TaskReviewResult,
        images=images or None,
        # 参考画像があるときは vision ルーターへ切り替える（docs/04-ai-pipeline.md 2.1）
        tier="vision" if images else "light",
        related_type="task",
        related_id=task.id,
        # 審査が失敗して業務トランザクションがロールバックしても監査ログは残す
        recorder=ai_invocation_repo.create_autonomous,
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
