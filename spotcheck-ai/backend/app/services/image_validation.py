"""機能B: VLMによる画像検品（docs/04-ai-pipeline.md 3節）。

提出画像（と参考画像）を base64 データURIで添付して VLM に判定させる。
参考画像がある場合は **1枚目を参考画像、2枚目を提出画像** として送り、順序をプロンプトで明示する。
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.storage import StorageBackend
from app.models import Submission, Task
from app.models.task import MAX_REFERENCE_IMAGES
from app.prompts.image_validation import SYSTEM_PROMPT, build_user_prompt
from app.repositories import ai_invocation_repo
from app.schemas.ai import ImageValidationResult
from app.services.orca_client import ImageInput, OrcaClient, encode_image_for_vlm

logger = get_logger(__name__)

JST = ZoneInfo("Asia/Tokyo")


def _jst_hour(value: datetime) -> int:
    """撮影時刻の「時」を日本時間で返す。"""
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return aware.astimezone(JST).hour


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

    result = await orca.complete_json(
        purpose="image_validation",
        system_prompt=SYSTEM_PROMPT,
        user_prompt=build_user_prompt(task, submission, has_reference=has_reference),
        response_schema=ImageValidationResult,
        images=images or None,
        tier="vision",
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
    parsed = result.parsed
    assert isinstance(parsed, ImageValidationResult)
    return parsed
