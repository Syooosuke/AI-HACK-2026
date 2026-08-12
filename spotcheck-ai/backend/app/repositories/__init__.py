"""DBアクセスを集約するリポジトリ層。サービス層からのみ呼ぶ（CLAUDE.md 5節）。"""

from app.repositories import (
    ai_invocation_repo,
    assignment_repo,
    like_repo,
    notification_repo,
    saved_search_repo,
    submission_repo,
    task_repo,
    user_repo,
)

__all__ = [
    "ai_invocation_repo",
    "assignment_repo",
    "like_repo",
    "notification_repo",
    "saved_search_repo",
    "submission_repo",
    "task_repo",
    "user_repo",
]
