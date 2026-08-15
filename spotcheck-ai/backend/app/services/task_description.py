"""依頼タイトルから短い詳細メッセージを生成する。"""

from app.prompts.task_description import SYSTEM_PROMPT, build_user_prompt
from app.repositories import ai_invocation_repo
from app.schemas.ai import TaskDescriptionGenerationResult
from app.services.orca_client import OrcaClient


async def generate(title: str, orca: OrcaClient) -> str:
    """OrcaRouterの軽量ルーターで編集可能な依頼文を生成する。"""
    normalized_title = title.strip()
    result = await orca.complete_json(
        purpose="task_description_generation",
        system_prompt=SYSTEM_PROMPT,
        user_prompt=build_user_prompt(normalized_title),
        response_schema=TaskDescriptionGenerationResult,
        tier="light",
        model_key="task_description",
        # 300 では**推論モデルへ振られたときに reasoning tokens だけで使い切り、本文が空**になる
        # （実測: orcarouter/auto と gemini 系で 8件中 7〜8件が finish_reason="length"）。
        # 生成する文は180文字以内なので、800 でも通常の出力量は変わらない
        max_tokens=800,
        related_type="task_draft",
        recorder=ai_invocation_repo.create_autonomous,
        context={"title": normalized_title},
    )
    parsed = result.parsed
    assert isinstance(parsed, TaskDescriptionGenerationResult)
    return parsed.description.strip()
