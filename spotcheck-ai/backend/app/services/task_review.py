"""機能A: 依頼コンテキスト審査（docs/04-ai-pipeline.md 2節）。

**LLMの `decision` をそのまま信用せず、サーバー側でこのモジュールが最終決定する。**
Phase 1 では OrcaClient のスタブ応答を使う（プロンプトの実装は Phase 3）。
"""

from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import AIServiceError
from app.core.logging import get_logger
from app.core.storage import StorageBackend
from app.models import NotificationType, Task, TaskStatus
from app.models.task import MAX_REFERENCE_IMAGES
from app.prompts.task_review import SYSTEM_PROMPT, build_user_prompt
from app.repositories import ai_invocation_repo
from app.schemas.ai import TaskReviewResult
from app.schemas.task import ReviewChecks, ReviewResult
from app.services import content_filter, notification_service
from app.services.orca_client import ImageInput, OrcaClient, OrcaResult, encode_image_for_vlm

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

#: 票が割れて同数になったときの優先順位。
#: **より慎重な側を採る。** 公開してしまってからでは取り返しがつかないのに対し、
#: 却下・情報補足は依頼者が書き直せば済むため。
_TIE_BREAK_ORDER = ("rejected", "needs_info", "approved")


def majority_decision(decisions: list[str]) -> str:
    """複数モデルの判定を多数決でまとめる。

    同数のときは `_TIE_BREAK_ORDER` の順に慎重な側を採る
    （2モデルで意見が割れたときは必ずこの経路になる）。
    """
    counts = Counter(decisions)
    top = max(counts.values())
    tied = [d for d in _TIE_BREAK_ORDER if counts.get(d) == top]
    return tied[0]


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


def _blocked_result(filtered: content_filter.FilterResult) -> TaskReviewResult:
    """決定論フィルタで弾いた依頼を、AIの判定結果と同じ形に整える。"""
    return TaskReviewResult(
        decision="rejected",
        score=0,
        safety="fail",
        validity="pass",
        risk="pass",
        duplication="pass",
        rejection_reason=filtered.reason,
        missing_info=[],
        summary="安全性の基準を満たさないため却下しました。",
    )


async def review_task(
    session: Session,
    task: Task,
    orca: OrcaClient,
    storage: StorageBackend | None = None,
) -> ReviewOutcome:
    """依頼を審査し、tasks の審査結果カラムと status を更新する。"""
    settings = get_settings()
    has_reference_images = bool(task.reference_images)

    # **AIより先に決定論のフィルタを通す。** スタブモードではLLMを呼ばないため、
    # ここを通さないと明らかに黒い依頼まで素通りしてしまう。
    filtered = content_filter.screen(task.title, task.description)
    if filtered.blocked:
        logger.warning(
            "依頼を安全フィルタで却下しました",
            extra={"task_id": str(task.id), "matched": list(filtered.matched)},
        )
        return _finalize(
            session,
            task=task,
            result=_blocked_result(filtered),
            decision="rejected",
            is_stub=orca.is_stub,
        )
    # スタブモードでは画像を送らないため、無駄なダウンロードを避ける
    images = await _load_reference_images(task, storage, skip=orca.is_stub)

    async def ask(model: str | None) -> OrcaResult:
        return await orca.complete_json(
            purpose="task_review",
            system_prompt=SYSTEM_PROMPT,
            user_prompt=build_user_prompt(task, has_reference_images=has_reference_images),
            response_schema=TaskReviewResult,
            images=images or None,
            # 参考画像があるときは vision ルーターへ切り替える（docs/04-ai-pipeline.md 2.1）
            tier="vision" if images else "light",
            model_key="task_review",
            model=model,
            related_type="task",
            related_id=task.id,
            # 審査が失敗して業務トランザクションがロールバックしても監査ログは残す
            recorder=ai_invocation_repo.create_autonomous,
        )

    # 主モデルに加え、合議用のモデルへ**同時に**問い合わせる。
    # 直列にすると待ち時間が人数分伸びるため、並行で投げる。
    jury = settings.orca_review_jury_models
    outcomes = await asyncio.gather(
        ask(None), *(ask(model) for model in jury), return_exceptions=True
    )

    results: list[TaskReviewResult] = []
    is_stub = orca.is_stub
    for outcome in outcomes:
        if isinstance(outcome, BaseException):
            # 1つ落ちても残りで判定する。全滅した場合のみ下で例外にする
            logger.warning("依頼審査の合議で1件失敗しました", extra={"task_id": str(task.id)})
            continue
        parsed = outcome.parsed
        assert isinstance(parsed, TaskReviewResult)
        results.append(parsed)
        is_stub = outcome.is_stub

    if not results:
        raise AIServiceError("依頼審査に失敗しました。")

    decisions = [decide(r, score_threshold=settings.task_review_score_threshold) for r in results]
    decision = majority_decision(decisions)
    # 採用した判定を出した回答のうち最初のものを、表示用の内容として使う
    result = next(r for r, d in zip(results, decisions, strict=True) if d == decision)

    if len(results) > 1:
        logger.info(
            "依頼審査を合議で決定しました",
            extra={"task_id": str(task.id), "votes": decisions, "decision": decision},
        )

    return _finalize(session, task=task, result=result, decision=decision, is_stub=is_stub)


def _finalize(
    session: Session,
    *,
    task: Task,
    result: TaskReviewResult,
    decision: str,
    is_stub: bool,
) -> ReviewOutcome:
    """審査結果を tasks へ書き戻し、通知を出して戻り値を組み立てる。

    AIの判定と決定論フィルタの却下で、保存する形をそろえるために切り出している。
    """
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
            "is_stub": is_stub,
        },
    )

    _notify_review_result(session, task=task, decision=decision, result=result)

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


_DECISION_TO_NOTIFICATION: dict[str, tuple[NotificationType, str]] = {
    "approved": (NotificationType.TASK_APPROVED, "依頼が公開されました"),
    "needs_info": (NotificationType.TASK_NEEDS_INFO, "依頼に補足情報が必要です"),
    "rejected": (NotificationType.TASK_REJECTED, "依頼が却下されました"),
}


def _notify_review_result(
    session: Session, *, task: Task, decision: str, result: TaskReviewResult
) -> None:
    notification_type, title = _DECISION_TO_NOTIFICATION[decision]
    if decision == "needs_info":
        body = "、".join(result.missing_info) or None
    elif decision == "rejected":
        body = result.rejection_reason
    else:
        body = task.title
    notification_service.notify(
        session,
        user_id=task.client_id,
        type=notification_type,
        title=title,
        body=body,
        task_id=task.id,
    )
