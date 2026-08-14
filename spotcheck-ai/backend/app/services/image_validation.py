"""機能B: VLMによる画像検品（docs/04-ai-pipeline.md 3節）。

提出画像（と参考画像）を base64 データURIで添付して VLM に判定させる。
参考画像がある場合は **1枚目を参考画像、2枚目を提出画像** として送り、順序をプロンプトで明示する。
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.core.storage import StorageBackend
from app.models import Submission, Task
from app.models.task import MAX_REFERENCE_IMAGES
from app.prompts.image_validation import SYSTEM_PROMPT, build_user_prompt
from app.repositories import ai_invocation_repo
from app.schemas.ai import ImageValidationResult
from app.services.orca_client import ImageInput, OrcaClient, OrcaResult, encode_image_for_vlm

logger = get_logger(__name__)

JST = ZoneInfo("Asia/Tokyo")

_PERSON_TERMS = ("人物", "人の顔", "顔が", "顔を", "通行人", "人が写")
_PERSON_REJECTION_TERMS = (
    "避け",
    "画面外",
    "写さない",
    "写り込",
    "邪魔",
    "妨げ",
    "人物なし",
    "建物のみ",
)


def _jst_hour(value: datetime) -> int:
    """撮影時刻の「時」を日本時間で返す。"""
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return aware.astimezone(JST).hour


async def _resolve_boundary(
    first_result: OrcaResult,
    *,
    ask: Callable[[str | None], Awaitable[OrcaResult]],
    submission_id: uuid.UUID,
    settings: Settings,
) -> OrcaResult:
    """スコアがしきい値の近くなら、追加で判定させて多数決にする。

    **同じ画像・同じプロンプト・temperature 0.2 でもスコアが割れる**ことを実測した
    （30 と 95 のように合否をまたぐ振れ幅）。ただし振れるのは境界付近だけで、
    明らかな合格・不合格は安定していた。そこで**境界だけ厚くする**。

    全件を3回呼べば確実だが、待っているのは現地のワーカーであり、
    待ち時間を3倍にする価値はない。
    """
    first = first_result.parsed
    assert isinstance(first, ImageValidationResult)
    jury = settings.orca_validation_jury_models
    threshold = settings.submission_score_threshold
    band = settings.orca_validation_boundary

    if not jury or abs(first.score - threshold) > band:
        return first_result

    extra = await asyncio.gather(*(ask(model) for model in jury), return_exceptions=True)
    votes: list[tuple[bool, OrcaResult]] = [(first.score >= threshold, first_result)]
    for outcome in extra:
        if isinstance(outcome, BaseException):
            logger.warning(
                "検品の再判定で1件失敗しました", extra={"submission_id": str(submission_id)}
            )
            continue
        parsed = outcome.parsed
        assert isinstance(parsed, ImageValidationResult)
        votes.append((parsed.score >= threshold, outcome))

    passes = sum(1 for ok, _ in votes if ok)
    verdict = passes * 2 > len(votes)
    logger.info(
        "検品を境界再判定で決定しました",
        extra={
            "submission_id": str(submission_id),
            "scores": [v[1].parsed.score for v in votes],  # type: ignore[union-attr]
            "verdict": "pass" if verdict else "fail",
        },
    )
    # 多数派と同じ側の判定を採用する（採点内容も多数派のものに揃える）
    return next(result for ok, result in votes if ok is verdict)


async def validate_image(
    session: Session,
    *,
    task: Task,
    submission: Submission,
    orca: OrcaClient,
    storage: StorageBackend,
) -> ImageValidationResult:
    settings = get_settings()
    images: list[ImageInput] = []

    if not orca.is_stub:
        # 1枚目: 参考画像（最大3枚。取得できなかったものはスキップ）
        for reference in task.reference_images[:MAX_REFERENCE_IMAGES]:
            try:
                payload = await storage.download(
                    bucket=settings.storage_bucket_processed, key=reference.image_url
                )
            except Exception:  # noqa: BLE001 - 参考画像が無くても検品は続行する
                logger.warning(
                    "参考画像を取得できませんでした",
                    extra={"task_id": str(task.id), "key": reference.image_url},
                )
                continue
            images.append(
                ImageInput(url=reference.image_url, base64_data=encode_image_for_vlm(payload))
            )

        # 2枚目: 提出画像（原本。検品はマスキング前の画像に対して行う）
        raw = await storage.download(
            bucket=settings.storage_bucket_raw, key=submission.raw_image_url
        )
        images.append(
            ImageInput(url=submission.raw_image_url, base64_data=encode_image_for_vlm(raw))
        )

    has_reference = len(images) > 1

    async def ask(model: str | None) -> OrcaResult:
        return await orca.complete_json(
            purpose="image_validation",
            system_prompt=SYSTEM_PROMPT,
            user_prompt=build_user_prompt(task, submission, has_reference=has_reference),
            response_schema=ImageValidationResult,
            images=images or None,
            tier="vision",
            model_key="image_validation",
            model=model,
            related_type="submission",
            related_id=submission.id,
            # 検品が失敗してロールバックされても監査ログは残す
            recorder=ai_invocation_repo.create_autonomous,
            # スタブが再撮影ループを再現するために提出回数を渡す（docs/04-ai-pipeline.md 1.4）。
            # 撮影時刻も渡し、スタブが返す daylight_state を実際の時間帯と矛盾させない
            # （矛盾すると C-5 の環境整合チェックが誤って不整合と判定する）。
            context={
                "attempt_no": submission.attempt_no,
                "captured_hour": _jst_hour(submission.captured_at),
            },
        )

    result = await _resolve_boundary(
        await ask(None), ask=ask, submission_id=submission.id, settings=settings
    )
    parsed = result.parsed
    assert isinstance(parsed, ImageValidationResult)
    _ignore_person_only_rejection(parsed, score_threshold=settings.submission_score_threshold)
    return parsed


def _ignore_person_only_rejection(result: ImageValidationResult, *, score_threshold: int) -> None:
    """人物の写り込みだけを理由にしたVLMの拒否を無効化する。

    対象自体が無い場合や、人物以外の品質問題が含まれる場合は補正しない。
    本当に対象が完全に隠れているケースは、プロンプトどおりVLMが
    「人物を避ける」ではなく対象の視認不能を理由として返す前提で維持する。
    """
    if not result.subject_present or not result.issues:
        return
    if any(issue.code not in {"OTHER", "OBSTRUCTED"} for issue in result.issues):
        return

    feedback = " ".join([result.summary, *(issue.message for issue in result.issues)])
    if not any(term in feedback for term in _PERSON_TERMS):
        return
    if not any(term in feedback for term in _PERSON_REJECTION_TERMS):
        return

    logger.warning(
        "人物の写り込みだけを理由にした検品拒否を無効化しました",
        extra={"original_score": result.score, "original_issues": len(result.issues)},
    )
    result.framing_ok = True
    result.issues = []
    result.score = max(result.score, score_threshold)
    result.summary = result.observed_scene[:60] or "依頼対象を確認しました。"
