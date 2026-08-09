"""画像検品のプロンプト（docs/04-ai-pipeline.md 3.2, 3.3）。

Phase 1 はスタブモードのみで動作するため、プロンプトは未実装のプレースホルダである。
TODO(phase-4): docs/04-ai-pipeline.md 3.2 のシステムプロンプトと 3.3 のユーザープロンプトを実装する。
"""

from __future__ import annotations

from app.models import Submission, Task

SYSTEM_PROMPT = "TODO(phase-4): docs/04-ai-pipeline.md 3.2 のシステムプロンプトを実装する。"


def build_user_prompt(task: Task, submission: Submission, *, has_reference: bool) -> str:
    """TODO(phase-4): docs/04-ai-pipeline.md 3.3 のテンプレートに置き換える。"""
    return (
        "TODO(phase-4): docs/04-ai-pipeline.md 3.3 のユーザープロンプトを実装する。 "
        f"(task_id={task.id}, attempt_no={submission.attempt_no}, has_reference={has_reference})"
    )
