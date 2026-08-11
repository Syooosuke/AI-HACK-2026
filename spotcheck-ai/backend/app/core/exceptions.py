"""アプリ独自の例外。

ルーター層・サービス層では常にこれらを送出し、`main.py` の例外ハンドラが
docs/03-api.md 1.2 のエラーレスポンス形式へ変換する。

    {"error": {"code": "TASK_NOT_FOUND", "message": "...", "details": {}}}
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """全アプリ例外の基底。`code` は docs/03-api.md 1.2 の一覧に準拠する。"""

    status_code: int = 500
    code: str = "INTERNAL_ERROR"
    message: str = "サーバー内部でエラーが発生しました。"

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.details = details or {}
        super().__init__(self.message)

    def to_payload(self) -> dict[str, Any]:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class ValidationError(AppError):
    status_code = 400
    code = "VALIDATION_ERROR"
    message = "入力内容に誤りがあります。"


class Unauthenticated(AppError):
    status_code = 401
    code = "UNAUTHENTICATED"
    message = "ユーザーを特定できません。"


class Forbidden(AppError):
    status_code = 403
    code = "FORBIDDEN"
    message = "この操作を行う権限がありません。"


class NotFound(AppError):
    status_code = 404
    code = "NOT_FOUND"
    message = "対象が見つかりません。"


class Conflict(AppError):
    """状態競合（TASK_FULL / ALREADY_ACCEPTED / INVALID_STATE など）。"""

    status_code = 409
    code = "INVALID_STATE"
    message = "現在の状態ではこの操作を行えません。"


class FileTooLarge(AppError):
    status_code = 413
    code = "FILE_TOO_LARGE"
    message = "画像サイズが上限を超えています。"


class StorageError(AppError):
    status_code = 500
    code = "STORAGE_ERROR"
    message = "画像の保存に失敗しました。"


class StorageObjectNotFound(StorageError):
    """指定したキーの画像が存在しない。保存や通信の失敗（500）とは区別する。"""

    status_code = 404
    code = "NOT_FOUND"
    message = "画像が見つかりません。"


class AIServiceError(AppError):
    status_code = 502
    code = "AI_SERVICE_ERROR"
    message = "AIの処理に失敗しました。しばらくしてからもう一度お試しください。"
