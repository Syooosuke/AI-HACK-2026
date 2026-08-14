"""機能D: プライバシー自動保護（docs/04-ai-pipeline.md 5節 / D-09）。

**検品合格後にのみ実行**する（不合格画像は納品されないため処理不要）。

| 対象 | 検出方法 | 処理 |
|---|---|---|
| 通行人の顔 | ローカルYOLO（face モデル） | ガウシアンぼかし。矩形を上下左右に10%拡張 |
| 人物全体 | person クラス | **ぼかさない**（工事状況の確認に必要） |
| ナンバープレート | 車両を検出し、VLMへ座標を問い合わせ | 黒塗り（完全マスク） |
| 表札・番地 | VLMへ座標を問い合わせ | ガウシアンぼかし |

重みが無い環境・Ultralytics 未導入の環境では、**例外を出さずスキップして警告ログを出す**
（`masking_result.skipped = true`）。デモを止めないための仕様。
"""

from __future__ import annotations

import io
import time
import uuid
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter

from app.core.config import get_settings
from app.core.exceptions import AIServiceError
from app.core.logging import get_logger
from app.prompts.masking import SYSTEM_PROMPT, build_user_prompt
from app.repositories import ai_invocation_repo
from app.schemas.ai import PrivacyRegion, PrivacyRegionList
from app.services.orca_client import (
    COORDINATE_MAX_TOKENS,
    ImageInput,
    OrcaClient,
    encode_image_for_vlm,
)

logger = get_logger(__name__)

#: 顔矩形の拡張率（上下左右に10%）
FACE_BOX_EXPANSION = 0.1
#: ぼかしカーネルの最小サイズ（px）
MIN_BLUR_KERNEL = 15
#: 車両として扱う COCO クラス名
VEHICLE_CLASSES = frozenset({"car", "truck", "bus", "motorcycle"})
#: 黒塗りにする種別（読み取れてしまうと即座に個人特定につながるもの）
BLACKOUT_KINDS = frozenset({"license_plate"})
#: VLM の座標を採用する最低確信度
MIN_REGION_CONFIDENCE = 0.3


@dataclass
class MaskingOutcome:
    """マスキング結果。`image` は加工後のJPEGバイト列（スキップ時は原本と同一）。"""

    image: bytes
    result: dict[str, Any] = field(default_factory=dict)

    @property
    def skipped(self) -> bool:
        return bool(self.result.get("skipped"))


# ----------------------------------------------------------------------
# YOLO モデルの読み込み（存在しなければ None）
# ----------------------------------------------------------------------
@dataclass
class _Models:
    general: Any | None
    face: Any | None
    reason: str | None


@lru_cache
def load_models() -> _Models:
    """Ultralytics と重みファイルを読み込む。失敗しても例外は出さない。"""
    settings = get_settings()
    try:
        from ultralytics import YOLO
    except ImportError:
        return _Models(None, None, "ultralytics が未導入のためマスキングをスキップします")

    def load(path_text: str, label: str) -> Any | None:
        path = Path(path_text)
        if not path.exists():
            logger.warning("YOLOの重みが見つかりません", extra={"model": label, "path": str(path)})
            return None
        try:
            return YOLO(str(path))
        except Exception:
            logger.exception("YOLOの重みを読み込めませんでした", extra={"model": label})
            return None

    general = load(settings.yolo_model_path, "general")
    face = load(settings.yolo_face_model_path, "face")
    if general is None and face is None:
        return _Models(None, None, "YOLOの重みが配置されていないためマスキングをスキップします")
    return _Models(general, face, None)


# ----------------------------------------------------------------------
async def apply_masking(
    image_bytes: bytes,
    *,
    orca: OrcaClient,
    submission_id: uuid.UUID | None = None,
) -> MaskingOutcome:
    """顔・ナンバープレート・表札を処理した画像と `masking_result` を返す。"""
    started = time.perf_counter()
    settings = get_settings()
    models = load_models()

    # スタブでは画像を解析できないため、YOLOも無い場合だけ従来どおりスキップする。
    # 実OrcaRouterが有効なら、YOLO重みが無くてもVLMの座標検出でマスキングを続行する。
    if models.general is None and models.face is None and orca.is_stub:
        logger.warning(models.reason or "マスキングをスキップします")
        return MaskingOutcome(
            image=image_bytes,
            result={
                "skipped": True,
                "reason": models.reason,
                "regions": [],
                "face_count": 0,
                "plate_count": 0,
                "processing_ms": _elapsed_ms(started),
            },
        )

    with Image.open(io.BytesIO(image_bytes)) as opened:
        image = opened.convert("RGB")

    width, height = image.size
    regions: list[dict[str, Any]] = []

    # --- 顔（ローカル推論） -------------------------------------------------
    face_boxes = _detect(models.face, image, settings.yolo_confidence_threshold)
    for box, _label in face_boxes:
        expanded = _expand(box, width, height, FACE_BOX_EXPANSION)
        _blur_region(image, expanded, settings.blur_kernel_ratio)
        regions.append(_region("face", "yolo_face", expanded, width, height, blurred=True))

    # 一般モデルの推論は1回だけ行い、結果を人物と車両へ振り分ける。
    general_detections = _detect(models.general, image, settings.yolo_confidence_threshold)

    # --- 人物（ぼかさない。検出結果のみ記録） --------------------------------
    person_boxes = [
        box for box, label in general_detections if label == "person"
    ]

    # --- 車両（プレート探索のヒントとして使う） ------------------------------
    vehicle_boxes = [
        box for box, label in general_detections if label in VEHICLE_CLASSES
    ]

    # --- ナンバープレート・表札（VLMへ座標を問い合わせる） --------------------
    plate_count = 0
    vlm_error: str | None = None
    try:
        privacy_regions = await _ask_privacy_regions(
            image_bytes,
            vehicle_boxes=[_normalize(box, width, height) for box in vehicle_boxes],
            orca=orca,
            submission_id=submission_id,
        )
    except AIServiceError as exc:
        # VLM呼び出しに失敗しても処理を止めず、YOLOで検出できた顔のみ処理する（5.2節）
        privacy_regions = []
        vlm_error = exc.message
        logger.warning("プライバシー領域の問い合わせに失敗しました", extra={"reason": exc.message})

    for region in privacy_regions:
        if region.confidence < MIN_REGION_CONFIDENCE:
            continue
        box = _denormalize(region, width, height)
        if box is None:
            continue
        if region.kind in BLACKOUT_KINDS:
            ImageDraw.Draw(image).rectangle(box, fill=(0, 0, 0))
            plate_count += 1
            regions.append(_region(region.kind, "vlm", box, width, height, blurred=True))
        else:
            _blur_region(image, box, settings.blur_kernel_ratio)
            regions.append(_region(region.kind, "vlm", box, width, height, blurred=True))

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=90)

    result = {
        "skipped": False,
        "regions": regions,
        "face_count": len(face_boxes),
        "person_count": len(person_boxes),
        "vehicle_count": len(vehicle_boxes),
        "plate_count": plate_count,
        "processing_ms": _elapsed_ms(started),
    }
    if models.general is None and models.face is None:
        result["yolo_skipped"] = True
        result["yolo_skip_reason"] = models.reason
    if vlm_error:
        result["vlm_error"] = vlm_error

    logger.info(
        "マスキングを適用しました",
        extra={
            "faces": len(face_boxes),
            "persons": len(person_boxes),
            "plates": plate_count,
            "regions": len(regions),
        },
    )
    return MaskingOutcome(image=buffer.getvalue(), result=result)


# ----------------------------------------------------------------------
async def _ask_privacy_regions(
    image_bytes: bytes,
    *,
    vehicle_boxes: list[tuple[float, float, float, float]],
    orca: OrcaClient,
    submission_id: uuid.UUID | None,
) -> list[PrivacyRegion]:
    result = await orca.complete_json(
        purpose="image_validation",
        system_prompt=SYSTEM_PROMPT,
        user_prompt=build_user_prompt(vehicle_boxes=vehicle_boxes),
        response_schema=PrivacyRegionList,
        images=[ImageInput(base64_data=encode_image_for_vlm(image_bytes))],
        tier="vision",
        max_tokens=COORDINATE_MAX_TOKENS,
        related_type="submission",
        related_id=submission_id,
        recorder=ai_invocation_repo.create_autonomous,
        context={"stage": "masking"},
    )
    parsed = result.parsed
    assert isinstance(parsed, PrivacyRegionList)
    return parsed.regions


def _detect(
    model: Any | None, image: Image.Image, confidence: float
) -> list[tuple[tuple[int, int, int, int], str]]:
    """(bbox, クラス名) のリストを返す。モデルが無い/失敗した場合は空。"""
    if model is None:
        return []
    try:
        predictions = model.predict(source=image, conf=confidence, verbose=False)
    except Exception:
        logger.exception("YOLOの推論に失敗しました")
        return []

    found: list[tuple[tuple[int, int, int, int], str]] = []
    names = getattr(model, "names", {}) or {}
    for prediction in predictions:
        boxes = getattr(prediction, "boxes", None)
        if boxes is None:
            continue
        for index in range(len(boxes)):
            x1, y1, x2, y2 = (float(value) for value in boxes.xyxy[index].tolist())
            class_id = int(boxes.cls[index].item()) if boxes.cls is not None else -1
            label = str(names.get(class_id, class_id))
            found.append(((int(x1), int(y1), int(x2), int(y2)), label))
    return found


def _expand(
    box: tuple[int, int, int, int], width: int, height: int, ratio: float
) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = box
    margin_x = int((x2 - x1) * ratio)
    margin_y = int((y2 - y1) * ratio)
    return (
        max(0, x1 - margin_x),
        max(0, y1 - margin_y),
        min(width, x2 + margin_x),
        min(height, y2 + margin_y),
    )


def _blur_region(image: Image.Image, box: tuple[int, int, int, int], ratio: float) -> None:
    """対象矩形の短辺 × ratio をカーネルサイズとし、奇数に丸める（最小15px）。"""
    x1, y1, x2, y2 = box
    if x2 <= x1 or y2 <= y1:
        return
    region = image.crop(box)
    kernel = max(MIN_BLUR_KERNEL, int(min(region.width, region.height) * ratio))
    if kernel % 2 == 0:
        kernel += 1
    # Pillow は半径指定のため、カーネルサイズの半分を半径として使う
    region = region.filter(ImageFilter.GaussianBlur(radius=max(1, kernel // 2)))
    image.paste(region, box)


def _normalize(
    box: tuple[int, int, int, int], width: int, height: int
) -> tuple[float, float, float, float]:
    x1, y1, x2, y2 = box
    return (x1 / width, y1 / height, x2 / width, y2 / height)


def _denormalize(
    region: PrivacyRegion, width: int, height: int
) -> tuple[int, int, int, int] | None:
    x1 = int(min(max(region.x1, 0.0), 1.0) * width)
    y1 = int(min(max(region.y1, 0.0), 1.0) * height)
    x2 = int(min(max(region.x2, 0.0), 1.0) * width)
    y2 = int(min(max(region.y2, 0.0), 1.0) * height)
    if x2 <= x1 or y2 <= y1:
        logger.warning("VLMが返した座標が不正なため無視します", extra={"kind": region.kind})
        return None
    return (x1, y1, x2, y2)


def _region(
    kind: str,
    method: str,
    box: tuple[int, int, int, int],
    width: int,
    height: int,
    *,
    blurred: bool,
) -> dict[str, Any]:
    normalized = _normalize(box, width, height)
    return {
        "kind": kind,
        "method": method,
        "bbox": [round(value, 4) for value in normalized],
        "blurred": blurred,
    }


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
