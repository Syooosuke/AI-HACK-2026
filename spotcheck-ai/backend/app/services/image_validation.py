"""機能B: VLMによる画像検品（docs/04-ai-pipeline.md 3節）。

Phase 1 では OrcaClient のスタブ応答を使う。
TODO(phase-4): 実画像を base64 で添付し、参考画像との順序を明示して送る実装に置き換える。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Submission, Task
from app.prompts.image_validation import SYSTEM_PROMPT, build_user_prompt
from app.repositories import ai_invocation_repo
from app.schemas.ai import ImageValidationResult
from app.services.orca_client import OrcaClient


async def validate_image(
    session: Session, *, task: Task, submission: Submission, orca: OrcaClient
) -> ImageValidationResult:
    has_reference = bool(task.reference_images)

    def recorder(**kwargs: object) -> None:
        ai_invocation_repo.create(session, **kwargs)  # type: ignore[arg-type]

    result = await orca.complete_json(
        purpose="image_validation",
        system_prompt=SYSTEM_PROMPT,
        user_prompt=build_user_prompt(task, submission, has_reference=has_reference),
        response_schema=ImageValidationResult,
        # TODO(phase-4): images に提出画像（と参考画像）を渡す
        tier="vision",
        related_type="submission",
        related_id=submission.id,
        recorder=recorder,
        # スタブが再撮影ループを再現するために提出回数を渡す（docs/04-ai-pipeline.md 1.4）
        context={"attempt_no": submission.attempt_no},
    )
    parsed = result.parsed
    assert isinstance(parsed, ImageValidationResult)
    return parsed
