"""投稿サムネイルの生成。

参考画像が無い依頼でも一覧に正方形の画像が並ぶようにする。段階的にフォールバックする。

1. 参考画像がある → その1枚目をサムネイルにする（source=reference）
2. 無い → ストリートビューを取得し、依頼文とあわせてAIに画像生成させる（source=generated）
3. 画像生成が使えない・失敗した → ストリートビュー画像をそのまま使う（source=streetview）
4. ストリートビューも取れない → 依頼のタイトルを描いたプレースホルダを作る（source=placeholder）

**この処理は失敗しても依頼の公開を妨げない。** BackgroundTasks から呼び出す。
"""

from __future__ import annotations

import io
import uuid
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_session_factory
from app.core.logging import get_logger
from app.core.storage import StorageBackend, get_storage
from app.models import Task
from app.prompts import thumbnail as prompts
from app.repositories import ai_invocation_repo, task_repo
from app.services import streetview
from app.services.orca_client import (
    ImageInput,
    OrcaClient,
    encode_image_for_vlm,
    get_orca_client,
)

logger = get_logger(__name__)

THUMBNAIL_PREFIX = "task-thumbnail"
JPEG_QUALITY = 88

#: 日本語を描けるフォントの候補。見つからない場合は英数字だけで描く。
CJK_FONT_CANDIDATES = (
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansJP-Regular.otf",
)

#: プレースホルダの背景色（依頼IDから決めて、依頼ごとに色が変わるようにする）
PLACEHOLDER_COLORS = (
    ((37, 99, 235), (30, 64, 175)),
    ((5, 150, 105), (4, 108, 78)),
    ((124, 58, 237), (91, 33, 182)),
    ((234, 88, 12), (154, 52, 18)),
)


class _SceneDescription(BaseModel):
    scene: str


# ----------------------------------------------------------------------
# 画像加工
# ----------------------------------------------------------------------
def to_square_jpeg(data: bytes, *, size: int) -> bytes:
    """中央を正方形に切り抜き、指定サイズのJPEGへ変換する。"""
    with Image.open(io.BytesIO(data)) as image:
        rgb = image.convert("RGB")
        edge = min(rgb.size)
        left = (rgb.width - edge) // 2
        top = (rgb.height - edge) // 2
        cropped = rgb.crop((left, top, left + edge, top + edge)).resize((size, size), Image.LANCZOS)
        buffer = io.BytesIO()
        cropped.save(buffer, format="JPEG", quality=JPEG_QUALITY)
    return buffer.getvalue()


def _load_font(size: int) -> tuple[ImageFont.ImageFont | ImageFont.FreeTypeFont, bool]:
    """日本語を描けるフォントを探す。戻り値は (フォント, 日本語が描けるか)。"""
    for path in CJK_FONT_CANDIDATES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size), True
            except OSError:
                continue
    return ImageFont.load_default(), False


def build_placeholder(task: Task, *, size: int) -> bytes:
    """外部サービスに頼らないサムネイル。依頼の場所と報酬を描く。

    日本語フォントが見つからない環境では英数字のみで描く（豆腐を出さない）。
    """
    start, end = PLACEHOLDER_COLORS[task.id.int % len(PLACEHOLDER_COLORS)]
    image = Image.new("RGB", (size, size), start)
    draw = ImageDraw.Draw(image)

    # 上下方向のグラデーション
    for y in range(size):
        ratio = y / max(1, size - 1)
        draw.line(
            [(0, y), (size, y)],
            fill=tuple(round(s + (e - s) * ratio) for s, e in zip(start, end, strict=True)),
        )

    # カメラを模した円（撮影依頼であることを示す）
    center = size // 2
    radius = size // 5
    draw.ellipse(
        [center - radius, center - radius * 1.1, center + radius, center + radius * 0.9],
        outline=(255, 255, 255),
        width=max(2, size // 100),
    )

    reward_font, has_cjk = _load_font(max(18, size // 12))
    small_font, _ = _load_font(max(12, size // 26))

    margin = size * 0.07
    reward = f"¥{task.reward_amount:,}" if has_cjk else f"{task.reward_amount} JPY"
    draw.text((margin, size * 0.74), reward, fill=(255, 255, 255), font=reward_font)

    place = task.location_address if has_cjk else None
    label = place or f"{task.location_lat:.4f}, {task.location_lng:.4f}"
    draw.text((margin, size * 0.86), label[:32], fill=(255, 255, 255), font=small_font)

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=JPEG_QUALITY)
    return buffer.getvalue()


# ----------------------------------------------------------------------
# 生成
# ----------------------------------------------------------------------
async def _describe_scene(
    session: Session, *, task: Task, image: bytes, orca: OrcaClient
) -> str | None:
    """ストリートビュー画像をVLMに読ませて、風景を一文で説明させる。"""
    try:
        result = await orca.complete_json(
            purpose="thumbnail_generation",
            system_prompt=prompts.SCENE_SYSTEM_PROMPT,
            user_prompt=prompts.build_scene_user_prompt(task),
            response_schema=_SceneDescription,
            images=[ImageInput(base64_data=encode_image_for_vlm(image))],
            tier="vision",
            recorder=ai_invocation_repo.create_autonomous,
            related_type="task",
            related_id=task.id,
        )
    except Exception:  # noqa: BLE001 - 説明が取れなくても生成は続ける
        logger.warning("風景の説明を取得できませんでした", extra={"task_id": str(task.id)})
        return None
    described = result.parsed
    return described.scene if isinstance(described, _SceneDescription) else None


async def _generate_from_scene(
    session: Session, *, task: Task, scene: str | None, orca: OrcaClient, size: int
) -> bytes | None:
    """AIに正方形のサムネイル画像を生成させる。使えない場合は None。"""
    if not orca.image_generation_enabled:
        logger.info(
            "画像生成が未設定のためストリートビュー画像を使います", extra={"task_id": str(task.id)}
        )
        return None
    try:
        generated = await orca.generate_image(
            prompt=prompts.build_image_prompt(task, scene),
            size=size,
            recorder=ai_invocation_repo.create_autonomous,
            related_type="task",
            related_id=task.id,
        )
    except Exception:  # noqa: BLE001 - 生成失敗はフォールバックで吸収する
        logger.warning("サムネイルの生成に失敗しました", extra={"task_id": str(task.id)})
        return None
    return generated.data


async def build_thumbnail(
    session: Session,
    *,
    task: Task,
    storage: StorageBackend,
    orca: OrcaClient,
) -> tuple[str, str] | None:
    """サムネイルを用意して (保存キー, 由来) を返す。参考画像がある場合はそれを使う。"""
    settings = get_settings()
    size = settings.thumbnail_size

    if task.reference_images:
        # 依頼と一緒に写真がアップロードされている場合はそれを見せる
        return task.reference_images[0].image_url, "reference"

    source_image = await streetview.fetch_image(
        lat=task.location_lat, lng=task.location_lng, size=size
    )

    payload: bytes | None = None
    origin = "placeholder"
    if source_image is not None:
        scene = await _describe_scene(session, task=task, image=source_image, orca=orca)
        generated = await _generate_from_scene(
            session, task=task, scene=scene, orca=orca, size=size
        )
        if generated is not None:
            payload, origin = generated, "generated"
        else:
            payload, origin = source_image, "streetview"

    if payload is None:
        payload, origin = build_placeholder(task, size=size), "placeholder"

    try:
        square = to_square_jpeg(payload, size=size)
    except Exception:  # noqa: BLE001 - 壊れた画像が来た場合はプレースホルダへ落とす
        logger.warning("サムネイルを変換できませんでした", extra={"task_id": str(task.id)})
        square = to_square_jpeg(build_placeholder(task, size=size), size=size)
        origin = "placeholder"

    key = f"{THUMBNAIL_PREFIX}/{task.id}.jpg"
    await storage.upload(
        bucket=settings.storage_bucket_processed,
        key=key,
        data=square,
        content_type="image/jpeg",
    )
    return key, origin


async def generate_for_task(task_id: uuid.UUID) -> None:
    """BackgroundTasks から呼ぶ入口。依頼のサムネイルを作って保存する。"""
    factory = get_session_factory()
    with factory() as session:
        task = task_repo.get(session, task_id)
        if task is None:
            logger.warning(
                "サムネイル生成対象の依頼が見つかりません", extra={"task_id": str(task_id)}
            )
            return
        if task.thumbnail_image_url:
            return  # すでに生成済み

        try:
            outcome = await build_thumbnail(
                session, task=task, storage=get_storage(), orca=get_orca_client()
            )
        except Exception:
            logger.exception("サムネイル生成に失敗しました", extra={"task_id": str(task_id)})
            return

        if outcome is None:
            return
        key, origin = outcome
        task.thumbnail_image_url = key
        task.thumbnail_source = origin
        session.commit()
        logger.info("サムネイルを保存しました", extra={"task_id": str(task_id), "source": origin})
