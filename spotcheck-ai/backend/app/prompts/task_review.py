"""依頼審査のプロンプト（docs/04-ai-pipeline.md 2.4, 2.5）。

Phase 1 はスタブモードのみで動作するため、プロンプトは未実装のプレースホルダである。
TODO(phase-3): docs/04-ai-pipeline.md 2.4 のシステムプロンプトと 2.5 のユーザープロンプトを実装する。
"""

from __future__ import annotations

from app.models import Task

SYSTEM_PROMPT = "TODO(phase-3): docs/04-ai-pipeline.md 2.4 のシステムプロンプトを実装する。"


def build_user_prompt(task: Task, *, has_reference_images: bool) -> str:
    """TODO(phase-3): docs/04-ai-pipeline.md 2.5 のテンプレートに置き換える。"""
    return (
        "TODO(phase-3): docs/04-ai-pipeline.md 2.5 のユーザープロンプトを実装する。 "
        f"(task_id={task.id}, has_reference_images={has_reference_images})"
    )
