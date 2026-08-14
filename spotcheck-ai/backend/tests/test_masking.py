"""プライバシー自動マスキングのテスト（docs/04-ai-pipeline.md 5節）。

YOLO の推論は差し替え、マスキングの適用ロジックを決定論的に検証する。
実モデルでの検出は実写画像を使ったライブ検証で確認する。
"""

from __future__ import annotations

import io
import json
from typing import Any

import httpx
import pytest
from PIL import Image

from app.core.config import get_settings
from app.services import masking
from app.services.masking import _Models, apply_masking
from app.services.orca_client import OrcaClient

GENERAL = "general-model"
FACE = "face-model"
SIZE = (400, 300)


def base_image() -> bytes:
    """左半分を細かい市松模様にした画像。ぼかしの効果が検出しやすい。"""
    image = Image.new("RGB", SIZE, (240, 240, 240))
    pixels = image.load()
    for y in range(SIZE[1]):
        for x in range(SIZE[0]):
            if (x // 2 + y // 2) % 2 == 0:
                pixels[x, y] = (10, 10, 10)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def variance(image: Image.Image, box: tuple[int, int, int, int]) -> float:
    """領域内の輝度のばらつき。ぼかすと小さくなる。"""
    region = image.crop(box).convert("L")
    values = list(region.tobytes())
    mean = sum(values) / len(values)
    return sum((value - mean) ** 2 for value in values) / len(values)


def install_models(
    monkeypatch: pytest.MonkeyPatch, *, faces: list, persons: list, vehicles: list
) -> None:
    monkeypatch.setattr(masking, "load_models", lambda: _Models(GENERAL, FACE, None))

    def fake_detect(model: Any, _image: Image.Image, _confidence: float):
        if model is FACE:
            return [(box, "FACE") for box in faces]
        return [(box, "person") for box in persons] + [(box, "car") for box in vehicles]

    monkeypatch.setattr(masking, "_detect", fake_detect)


def install_vlm(
    monkeypatch: pytest.MonkeyPatch, regions: list[dict] | None, *, fail: bool = False
) -> OrcaClient:
    settings = get_settings()
    monkeypatch.setattr(settings, "orca_stub_mode", False)
    monkeypatch.setattr(settings, "orca_api_key", "test-key")

    def handler(_request: httpx.Request) -> httpx.Response:
        if fail:
            return httpx.Response(401, text="Invalid token")
        content = json.dumps({"regions": regions or []}, ensure_ascii=False)
        return httpx.Response(
            200,
            json={
                "id": "x",
                "model": "vision-model",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": content}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )

    return OrcaClient(transport=httpx.MockTransport(handler))


# ----------------------------------------------------------------------
async def test_skips_without_weights(monkeypatch: pytest.MonkeyPatch) -> None:
    """重みが無い環境でも例外を出さずスキップし、理由を記録する（完了条件③）。"""
    monkeypatch.setattr(
        masking, "load_models", lambda: _Models(None, None, "重みが配置されていません")
    )
    settings = get_settings()
    monkeypatch.setattr(settings, "orca_stub_mode", True)
    orca = OrcaClient()
    original = base_image()

    outcome = await apply_masking(original, orca=orca)

    assert outcome.skipped is True
    assert outcome.result["reason"] == "重みが配置されていません"
    assert outcome.result["regions"] == []
    assert outcome.result["face_count"] == 0
    # 画像はそのまま返る（加工しない）
    assert outcome.image == original


async def test_uses_vlm_when_yolo_weights_are_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """実OrcaRouterが有効なら、YOLOなしでもVLMで顔を検出してぼかす。"""
    monkeypatch.setattr(
        masking, "load_models", lambda: _Models(None, None, "重みが配置されていません")
    )
    face_box = (20, 20, 80, 80)
    orca = install_vlm(
        monkeypatch,
        [
            {
                "kind": "face",
                "x1": face_box[0] / SIZE[0],
                "y1": face_box[1] / SIZE[1],
                "x2": face_box[2] / SIZE[0],
                "y2": face_box[3] / SIZE[1],
                "confidence": 0.9,
            }
        ],
    )

    outcome = await apply_masking(base_image(), orca=orca)

    assert outcome.skipped is False
    assert outcome.result["yolo_skipped"] is True
    assert outcome.result["face_count"] == 0
    face = next(region for region in outcome.result["regions"] if region["kind"] == "face")
    assert face["method"] == "vlm"
    with Image.open(io.BytesIO(outcome.image)) as masked:
        assert variance(masked, face_box) < 200


async def test_blurs_faces_but_not_persons(monkeypatch: pytest.MonkeyPatch) -> None:
    """通行人の顔はぼかし、人物の全身はぼかさない（完了条件①）。"""
    face_box = (20, 20, 80, 80)
    person_box = (200, 100, 320, 280)
    install_models(monkeypatch, faces=[face_box], persons=[person_box], vehicles=[])
    orca = install_vlm(monkeypatch, [])
    original = base_image()

    outcome = await apply_masking(original, orca=orca)

    assert outcome.skipped is False
    assert outcome.result["face_count"] == 1
    assert outcome.result["person_count"] == 1
    kinds = [region["kind"] for region in outcome.result["regions"]]
    assert kinds == ["face"]  # 人物はマスキング対象に含めない

    with Image.open(io.BytesIO(outcome.image)) as masked:
        # 顔の領域はぼけて分散が下がる
        assert variance(masked, face_box) < 200
        # 人物の領域は元の細かい模様が残る
        assert variance(masked, person_box) > 1000


async def test_license_plate_is_blacked_out(monkeypatch: pytest.MonkeyPatch) -> None:
    """ナンバープレートは黒塗り（完全マスク）にする（完了条件②）。"""
    install_models(monkeypatch, faces=[], persons=[], vehicles=[(100, 100, 300, 250)])
    orca = install_vlm(
        monkeypatch,
        [{"kind": "license_plate", "x1": 0.4, "y1": 0.6, "x2": 0.6, "y2": 0.7, "confidence": 0.9}],
    )

    outcome = await apply_masking(base_image(), orca=orca)

    assert outcome.result["plate_count"] == 1
    assert outcome.result["vehicle_count"] == 1
    plate = next(r for r in outcome.result["regions"] if r["kind"] == "license_plate")
    assert plate["method"] == "vlm"

    with Image.open(io.BytesIO(outcome.image)) as masked:
        box = (
            int(0.4 * SIZE[0]) + 4,
            int(0.6 * SIZE[1]) + 2,
            int(0.6 * SIZE[0]) - 4,
            int(0.7 * SIZE[1]) - 2,
        )
        pixels = list(masked.crop(box).convert("L").tobytes())
        assert max(pixels) < 20  # 黒で塗りつぶされている


async def test_nameplate_is_blurred_not_blacked_out(monkeypatch: pytest.MonkeyPatch) -> None:
    install_models(monkeypatch, faces=[], persons=[], vehicles=[])
    orca = install_vlm(
        monkeypatch,
        [{"kind": "nameplate", "x1": 0.1, "y1": 0.1, "x2": 0.3, "y2": 0.25, "confidence": 0.8}],
    )

    outcome = await apply_masking(base_image(), orca=orca)

    region = next(r for r in outcome.result["regions"] if r["kind"] == "nameplate")
    assert region["blurred"] is True
    assert outcome.result["plate_count"] == 0

    with Image.open(io.BytesIO(outcome.image)) as masked:
        box = (int(0.1 * SIZE[0]), int(0.1 * SIZE[1]), int(0.3 * SIZE[0]), int(0.25 * SIZE[1]))
        pixels = list(masked.crop(box).convert("L").tobytes())
        # 黒塗りではなくぼかしなので、平均は中間色になる
        assert 40 < sum(pixels) / len(pixels) < 220
        assert variance(masked, box) < 400


async def test_continues_with_faces_when_vlm_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """VLM呼び出しに失敗しても処理を止めず、顔だけ処理する（5.2節）。"""
    face_box = (20, 20, 80, 80)
    install_models(monkeypatch, faces=[face_box], persons=[], vehicles=[])
    orca = install_vlm(monkeypatch, None, fail=True)

    outcome = await apply_masking(base_image(), orca=orca)

    assert outcome.skipped is False
    assert outcome.result["face_count"] == 1
    assert outcome.result["plate_count"] == 0
    assert "vlm_error" in outcome.result
    with Image.open(io.BytesIO(outcome.image)) as masked:
        assert variance(masked, face_box) < 200


async def test_low_confidence_and_invalid_boxes_are_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_models(monkeypatch, faces=[], persons=[], vehicles=[])
    orca = install_vlm(
        monkeypatch,
        [
            # 確信度が低い
            {
                "kind": "license_plate",
                "x1": 0.1,
                "y1": 0.1,
                "x2": 0.2,
                "y2": 0.2,
                "confidence": 0.1,
            },
            # 座標が反転している
            {"kind": "nameplate", "x1": 0.8, "y1": 0.8, "x2": 0.2, "y2": 0.2, "confidence": 0.9},
        ],
    )

    outcome = await apply_masking(base_image(), orca=orca)

    assert outcome.result["regions"] == []
    assert outcome.result["plate_count"] == 0
