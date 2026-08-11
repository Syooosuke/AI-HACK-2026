"""ローカルストレージの加工済み画像を配信する開発用エンドポイント。"""

from fastapi import APIRouter
from fastapi.responses import Response

from app.core.config import get_settings
from app.core.exceptions import Forbidden
from app.core.storage import get_storage

router = APIRouter(prefix="/api/files", tags=["files"])


@router.get("/{bucket}/{key:path}", response_class=Response)
async def get_processed_file(bucket: str, key: str) -> Response:
    """加工済み画像だけを返す。原本バケットはURLを推測されても公開しない。"""
    settings = get_settings()
    if bucket != settings.storage_bucket_processed:
        raise Forbidden("原本画像にはアクセスできません。")

    payload = await get_storage().download(bucket=bucket, key=key)
    return Response(
        content=payload,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=3600"},
    )
