"""OrcaRouterを使ったクライアント向け調査結果総括。"""

from app.models import Submission, Task
from app.prompts.result_summary import SYSTEM_PROMPT, build_user_prompt
from app.repositories import ai_invocation_repo
from app.schemas.ai import ResultSummaryResult
from app.services.orca_client import ImageInput, OrcaClient, encode_image_for_vlm


async def generate_result_summary(
    *,
    task: Task,
    submission: Submission,
    processed_image: bytes,
    observations: list[str],
    orca: OrcaClient,
) -> str:
    """安全処理済み画像をOrcaRouterへ送り、画像に基づく総括を生成する。"""
    response = await orca.complete_json(
        purpose="result_summary",
        system_prompt=SYSTEM_PROMPT,
        user_prompt=build_user_prompt(task, observations),
        images=[ImageInput(base64_data=encode_image_for_vlm(processed_image))],
        response_schema=ResultSummaryResult,
        tier="vision",
        model_key="result_summary",
        related_type="submission",
        related_id=submission.id,
        recorder=ai_invocation_repo.create_autonomous,
        # スタブでも依頼ごとに違う総括を返せるようにする。固定文だと、どの依頼でも
        # 「工事は予定通り」と出てしまい、内容を読んでいないことが露骨に分かる
        context={"title": task.title, "observations": observations},
    )
    result = response.parsed
    assert isinstance(result, ResultSummaryResult)
    return result.summary.strip()
