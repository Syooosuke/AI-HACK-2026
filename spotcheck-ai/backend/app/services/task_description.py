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
        max_tokens=300,
        related_type="task_draft",
        recorder=ai_invocation_repo.create_autonomous,
        context={"title": normalized_title},
    )
    parsed = result.parsed
    assert isinstance(parsed, TaskDescriptionGenerationResult)
    return parsed.description.strip()
