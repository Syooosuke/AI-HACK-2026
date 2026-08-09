"""アップロード画像の共通検証。"""

from __future__ import annotations

from fastapi import UploadFile

from app.core.config import get_settings
from app.core.exceptions import FileTooLarge, ValidationError


async def read_and_validate_image(upload: UploadFile, *, field: str = "image") -> tuple[bytes, str]:
    """画像を読み込み、MIMEタイプとサイズを検証して (バイト列, content_type) を返す。"""
    settings = get_settings()
    content_type = (upload.content_type or "").lower()
    if content_type not in settings.allowed_image_type_list:
        raise ValidationError(
            f"対応していない画像形式です（{settings.allowed_image_types} のみ）。",
            details={"field": field, "contentType": content_type},
        )

    data = await upload.read()
    if not data:
        raise ValidationError("画像が空です。", details={"field": field})
    if len(data) > settings.max_upload_size_bytes:
        raise FileTooLarge(
            f"画像サイズが上限（{settings.max_upload_size_mb}MB）を超えています。",
            details={"field": field, "sizeBytes": len(data)},
        )
    return data, content_type


def extension_for(content_type: str) -> str:
    return {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
    }.get(content_type, "bin")
