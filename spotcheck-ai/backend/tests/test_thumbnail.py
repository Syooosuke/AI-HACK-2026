"""投稿サムネイル生成のテスト。

外部（Street View / 画像生成）が使えない環境でも必ず正方形の画像ができることを確認する。
"""

from __future__ import annotations

import io

import httpx
import pytest
from PIL import Image
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.storage import get_storage
from app.models import User
from app.services import streetview, thumbnail_service
from app.services.orca_client import GeneratedImage, OrcaClient
from tests.conftest import make_task, tiny_jpeg


def wide_jpeg() -> bytes:
    """正方形でない画像（切り抜きの確認用）。"""
    buffer = io.BytesIO()
    Image.new("RGB", (800, 300), (10, 120, 200)).save(buffer, format="JPEG")
    return buffer.getvalue()


# ----------------------------------------------------------------------
# 画像加工
# ----------------------------------------------------------------------
def test_to_square_jpeg_crops_to_square() -> None:
    square = thumbnail_service.to_square_jpeg(wide_jpeg(), size=320)
    with Image.open(io.BytesIO(square)) as image:
        assert image.size == (320, 320)
        assert image.format == "JPEG"


def test_placeholder_is_square(session: Session, users: dict[str, User]) -> None:
    task = make_task(session, client=users["client"])
    placeholder = thumbnail_service.build_placeholder(task, size=256)
    with Image.open(io.BytesIO(placeholder)) as image:
        assert image.size == (256, 256)


def test_placeholder_without_cjk_font_is_still_square(
    session: Session, users: dict[str, User], monkeypatch: pytest.MonkeyPatch
) -> None:
    """日本語フォントが無い環境でも豆腐を描かず、画像自体は成立する。"""
    monkeypatch.setattr(thumbnail_service, "CJK_FONT_CANDIDATES", ())
    task = make_task(session, client=users["client"])

    placeholder = thumbnail_service.build_placeholder(task, size=256)

    with Image.open(io.BytesIO(placeholder)) as image:
        assert image.size == (256, 256)


def test_placeholder_color_depends_on_task(session: Session, users: dict[str, User]) -> None:
    """依頼ごとに色が変わる（同じ依頼なら常に同じ色）。"""
    first = make_task(session, client=users["client"])
    second = make_task(session, client=users["client"])
    assert thumbnail_service.build_placeholder(
        first, size=64
    ) == thumbnail_service.build_placeholder(first, size=64)
    # IDが違えば別の色になりうる（同じ色に落ちる可能性もあるため厳密比較はしない）
    assert isinstance(thumbnail_service.build_placeholder(second, size=64), bytes)


# ----------------------------------------------------------------------
# フォールバックの段階
# ----------------------------------------------------------------------
async def test_reference_image_is_used_when_present(
    session: Session, users: dict[str, User]
) -> None:
    """参考画像がある依頼はその1枚目をサムネイルにする（生成しない）。"""
    from app.repositories import task_repo

    task = make_task(session, client=users["client"])
    task_repo.add_reference_image(session, task_id=task.id, image_url="ref/1.jpg", sort_order=0)
    session.commit()
    session.refresh(task)

    outcome = await thumbnail_service.build_thumbnail(
        session, task=task, storage=get_storage(), orca=OrcaClient()
    )

    assert outcome == ("ref/1.jpg", "reference")


async def test_falls_back_to_placeholder_without_streetview(
    session: Session, users: dict[str, User], monkeypatch: pytest.MonkeyPatch
) -> None:
    """ストリートビューが使えない場合はプレースホルダを保存する。"""
    task = make_task(session, client=users["client"])

    async def no_streetview(**_kwargs: object) -> None:
        return None

    monkeypatch.setattr(streetview, "fetch_image", no_streetview)

    key, origin = await thumbnail_service.build_thumbnail(
        session, task=task, storage=get_storage(), orca=OrcaClient()
    )

    assert origin == "placeholder"
    assert key == f"{thumbnail_service.THUMBNAIL_PREFIX}/{task.id}.jpg"
    stored = await get_storage().download(bucket=get_settings().storage_bucket_processed, key=key)
    with Image.open(io.BytesIO(stored)) as image:
        assert image.size == (get_settings().thumbnail_size, get_settings().thumbnail_size)


async def test_uses_streetview_when_generation_disabled(
    session: Session, users: dict[str, User], monkeypatch: pytest.MonkeyPatch
) -> None:
    """画像生成が未設定なら、ストリートビュー画像をそのまま正方形にして使う。"""
    task = make_task(session, client=users["client"])

    async def street_image(**_kwargs: object) -> bytes:
        return wide_jpeg()

    monkeypatch.setattr(streetview, "fetch_image", street_image)
    orca = OrcaClient()
    monkeypatch.setattr(type(orca), "image_generation_enabled", property(lambda _self: False))

    key, origin = await thumbnail_service.build_thumbnail(
        session, task=task, storage=get_storage(), orca=orca
    )

    assert origin == "streetview"
    stored = await get_storage().download(bucket=get_settings().storage_bucket_processed, key=key)
    with Image.open(io.BytesIO(stored)) as image:
        assert image.width == image.height


async def test_uses_generated_image_when_available(
    session: Session, users: dict[str, User], monkeypatch: pytest.MonkeyPatch
) -> None:
    """画像生成が使える場合は生成結果を保存する。"""
    task = make_task(session, client=users["client"])

    async def street_image(**_kwargs: object) -> bytes:
        return wide_jpeg()

    async def generated(**_kwargs: object) -> GeneratedImage:
        return GeneratedImage(data=tiny_jpeg(), model="stub-image", latency_ms=1)

    monkeypatch.setattr(streetview, "fetch_image", street_image)
    orca = OrcaClient()
    monkeypatch.setattr(type(orca), "image_generation_enabled", property(lambda _self: True))
    monkeypatch.setattr(orca, "generate_image", generated)

    _key, origin = await thumbnail_service.build_thumbnail(
        session, task=task, storage=get_storage(), orca=orca
    )

    assert origin == "generated"


async def test_generation_failure_falls_back_to_streetview(
    session: Session, users: dict[str, User], monkeypatch: pytest.MonkeyPatch
) -> None:
    task = make_task(session, client=users["client"])

    async def street_image(**_kwargs: object) -> bytes:
        return wide_jpeg()

    async def failing(**_kwargs: object) -> GeneratedImage:
        raise RuntimeError("生成に失敗")

    monkeypatch.setattr(streetview, "fetch_image", street_image)
    orca = OrcaClient()
    monkeypatch.setattr(type(orca), "image_generation_enabled", property(lambda _self: True))
    monkeypatch.setattr(orca, "generate_image", failing)

    _key, origin = await thumbnail_service.build_thumbnail(
        session, task=task, storage=get_storage(), orca=orca
    )

    assert origin == "streetview"


async def test_generate_for_task_saves_source(
    session: Session, users: dict[str, User], monkeypatch: pytest.MonkeyPatch
) -> None:
    """BackgroundTasks の入口が依頼へ保存結果を書き戻す。"""
    task = make_task(session, client=users["client"])

    async def no_streetview(**_kwargs: object) -> None:
        return None

    monkeypatch.setattr(streetview, "fetch_image", no_streetview)

    await thumbnail_service.generate_for_task(task.id)
    session.expire_all()
    session.refresh(task)

    assert task.thumbnail_source == "placeholder"
    assert task.thumbnail_image_url is not None


# ----------------------------------------------------------------------
# ストリートビュー
# ----------------------------------------------------------------------
async def test_streetview_returns_none_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "google_maps_server_api_key", "")
    assert await streetview.fetch_image(lat=35.6595, lng=139.7005) is None


async def test_streetview_returns_none_when_zero_results(monkeypatch: pytest.MonkeyPatch) -> None:
    """パノラマが存在しない地点では取得しない（無駄な課金を避ける）。"""
    settings = get_settings()
    monkeypatch.setattr(settings, "google_maps_server_api_key", "test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        assert "metadata" in str(request.url)
        return httpx.Response(200, json={"status": "ZERO_RESULTS"})

    result = await streetview.fetch_image(lat=0.0, lng=0.0, transport=httpx.MockTransport(handler))
    assert result is None


async def test_streetview_returns_image_when_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "google_maps_server_api_key", "test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        if "metadata" in str(request.url):
            return httpx.Response(200, json={"status": "OK"})
        return httpx.Response(200, content=tiny_jpeg())

    result = await streetview.fetch_image(
        lat=35.6595, lng=139.7005, transport=httpx.MockTransport(handler)
    )
    assert result == tiny_jpeg()
