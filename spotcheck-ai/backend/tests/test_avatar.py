"""アバター画像のアップロード・配信・削除（`/api/users/*/avatar`）。"""

from __future__ import annotations

import io
from pathlib import Path

import httpx
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.main import app
from app.models import User
from app.services.avatar_service import AVATAR_SIZE
from tests.conftest import auth_headers, tiny_jpeg


def upload(
    client: TestClient, user: User, payload: bytes, content_type: str = "image/jpeg"
) -> httpx.Response:
    return client.post(
        "/api/users/me/avatar",
        headers=auth_headers(user),
        files={"image": ("avatar.jpg", payload, content_type)},
    )


def stored_path(key: str) -> Path:
    """ローカルストレージ上の保存先（差し替え時に古い画像が消えたかの確認用）。"""
    settings = get_settings()
    return Path(settings.local_storage_dir) / settings.storage_bucket_processed / key


def test_upload_sets_avatar_and_returns_url(users: dict[str, User], session: Session) -> None:
    worker = users["worker"]

    with TestClient(app) as client:
        response = upload(client, worker, tiny_jpeg(size=(200, 120)))
        assert response.status_code == 200
        avatar_url = response.json()["user"]["avatarUrl"]
        assert avatar_url is not None
        assert avatar_url.startswith(f"/api/users/{worker.id}/avatar?v=")

        # 認証なしでも配信され、正方形に整えられている
        image_response = client.get(avatar_url)
        assert image_response.status_code == 200
        assert image_response.headers["content-type"] == "image/jpeg"
        with Image.open(io.BytesIO(image_response.content)) as image:
            assert image.size == (AVATAR_SIZE, AVATAR_SIZE)

    session.refresh(worker)
    assert worker.avatar_url is not None
    assert worker.avatar_url.startswith(f"user-avatar/{worker.id}/")


def test_upload_replaces_previous_image(users: dict[str, User], session: Session) -> None:
    """差し替えるとURLの版が変わり、ストレージ上の古い画像は残さない。"""
    worker = users["worker"]

    with TestClient(app) as client:
        first = upload(client, worker, tiny_jpeg(color=(10, 20, 30))).json()["user"]["avatarUrl"]
        session.refresh(worker)
        old_key = worker.avatar_url

        second = upload(client, worker, tiny_jpeg(color=(200, 210, 220))).json()["user"][
            "avatarUrl"
        ]
        assert first != second
        assert client.get(second).status_code == 200

    session.refresh(worker)
    assert old_key is not None
    assert worker.avatar_url != old_key
    assert not stored_path(old_key).exists()


def test_delete_resets_to_default(users: dict[str, User], session: Session) -> None:
    worker = users["worker"]

    with TestClient(app) as client:
        avatar_url = upload(client, worker, tiny_jpeg()).json()["user"]["avatarUrl"]

        response = client.delete("/api/users/me/avatar", headers=auth_headers(worker))
        assert response.status_code == 200
        assert response.json()["user"]["avatarUrl"] is None

        assert client.get(avatar_url).status_code == 404

    session.refresh(worker)
    assert worker.avatar_url is None


def test_avatar_of_user_without_image_is_404(users: dict[str, User]) -> None:
    with TestClient(app) as client:
        response = client.get(f"/api/users/{users['client'].id}/avatar")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_unsupported_content_type_is_rejected(users: dict[str, User]) -> None:
    with TestClient(app) as client:
        response = upload(client, users["worker"], b"GIF89a", content_type="image/gif")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_upload_requires_authentication() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/users/me/avatar", files={"image": ("a.jpg", tiny_jpeg(), "image/jpeg")}
        )
    assert response.status_code == 401


def test_me_exposes_avatar_url(users: dict[str, User]) -> None:
    """ログイン後に取り直すユーザー情報にもアバターURLが載る。"""
    worker = users["worker"]
    with TestClient(app) as client:
        upload(client, worker, tiny_jpeg())
        response = client.get("/api/auth/me", headers=auth_headers(worker))

    assert response.status_code == 200
    assert response.json()["user"]["avatarUrl"].startswith(f"/api/users/{worker.id}/avatar")
