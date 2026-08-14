"""依頼作成APIのテスト（docs/03-api.md 3.1, 3.2）。

AI応答だけを差し替え、HTTP経路（multipart受付 → 審査 → status反映 → レスポンス）を検証する。
"""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes import tasks as tasks_route
from app.core.config import get_settings
from app.main import app
from app.models import Task, User
from app.services.orca_client import OrcaClient
from tests.conftest import CLIENT_ID, auth_headers


def llm_output(**overrides: Any) -> str:
    payload = {
        "decision": "approved",
        "score": 85,
        "safety": "pass",
        "validity": "pass",
        "risk": "pass",
        "duplication": "pass",
        "rejection_reason": None,
        "missing_info": [],
        "summary": "駅前の工事の進捗を確認する依頼です。",
    }
    payload.update(overrides)
    return json.dumps(payload, ensure_ascii=False)


def install_orca(monkeypatch: pytest.MonkeyPatch, *contents: str) -> None:
    """ルーターが使う OrcaClient を、応答を固定したものに差し替える。"""
    settings = get_settings()
    monkeypatch.setattr(settings, "orca_stub_mode", False)
    monkeypatch.setattr(settings, "orca_api_key", "test-key")

    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        index = min(calls["n"], len(contents) - 1)
        calls["n"] += 1
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "model": "grok/grok-4.5",
                "choices": [
                    {"index": 0, "message": {"role": "assistant", "content": contents[index]}}
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
            },
        )

    client = OrcaClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(tasks_route, "get_orca_client", lambda: client)


def form_data() -> dict[str, str]:
    now = datetime.now(UTC)
    return {
        "title": "駅前の再開発工事の進捗確認",
        "description": "渋谷駅前の再開発工事について、進捗と交通状況が分かるよう正面から撮影してください。",
        "locationLat": "35.6595",
        "locationLng": "139.7005",
        "locationAddress": "東京都渋谷区道玄坂1丁目",
        "scheduledAt": (now + timedelta(hours=1)).isoformat(),
        "deadlineAt": (now + timedelta(hours=6)).isoformat(),
        "rewardAmount": "2000",
        "requiredWorkerCount": "1",
    }


def reference_image() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (400, 300), (20, 100, 180)).save(buffer, format="JPEG")
    return buffer.getvalue()


HEADERS = auth_headers(CLIENT_ID)


def test_generate_short_description_from_title(
    session: Session, users: dict[str, User], monkeypatch: pytest.MonkeyPatch
) -> None:
    generated = (
        "駅前の工事現場を正面から撮影し、建物全体と現在の進捗状況が分かる写真を提出してください。"
    )
    install_orca(monkeypatch, json.dumps({"description": generated}, ensure_ascii=False))
    calls: list[dict[str, Any]] = []
    original = OrcaClient.complete_json

    async def spy(self: OrcaClient, **kwargs: Any):
        calls.append(kwargs)
        return await original(self, **kwargs)

    monkeypatch.setattr(OrcaClient, "complete_json", spy)

    with TestClient(app) as client:
        response = client.post(
            "/api/tasks/generate-description",
            headers=HEADERS,
            json={"title": "駅前の再開発工事の進捗確認"},
        )

    assert response.status_code == 200
    assert response.json() == {"description": generated}
    assert calls[0]["purpose"] == "task_description_generation"
    assert calls[0]["tier"] == "light"
    # 300 では推論モデルへ振られたとき reasoning tokens だけで使い切り、本文が空で返る
    assert calls[0]["max_tokens"] == 800
    assert "駅前の再開発工事の進捗確認" in calls[0]["user_prompt"]


def test_generate_description_requires_login_and_valid_title(
    session: Session, users: dict[str, User]
) -> None:
    with TestClient(app) as client:
        unauthenticated = client.post(
            "/api/tasks/generate-description", json={"title": "工事状況の確認"}
        )
        empty_title = client.post(
            "/api/tasks/generate-description", headers=HEADERS, json={"title": ""}
        )

    assert unauthenticated.status_code == 401
    assert empty_title.status_code == 400


def test_create_task_publishes_on_approval(
    session: Session, users: dict[str, User], monkeypatch: pytest.MonkeyPatch
) -> None:
    install_orca(monkeypatch, llm_output())

    with TestClient(app) as client:
        response = client.post("/api/tasks", headers=HEADERS, data=form_data())

    assert response.status_code == 201
    body = response.json()
    assert body["task"]["status"] == "open"
    assert body["task"]["reviewScore"] == 85
    assert body["review"]["decision"] == "approved"
    assert body["review"]["checks"] == {
        "safety": "pass",
        "validity": "pass",
        "risk": "pass",
        "duplication": "pass",
    }


def test_create_task_with_reference_image_uses_vision_router(
    session: Session, users: dict[str, User], monkeypatch: pytest.MonkeyPatch
) -> None:
    """参考画像があるときは vision ルーターへ切り替え、画像を添付して送る。"""
    install_orca(monkeypatch, llm_output())
    sent: list[dict[str, Any]] = []
    original = OrcaClient.complete_json

    async def spy(self: OrcaClient, **kwargs: Any):
        sent.append(kwargs)
        return await original(self, **kwargs)

    monkeypatch.setattr(OrcaClient, "complete_json", spy)

    with TestClient(app) as client:
        response = client.post(
            "/api/tasks",
            headers=HEADERS,
            data=form_data(),
            files=[("referenceImages", ("ref.jpg", reference_image(), "image/jpeg"))],
        )

    assert response.status_code == 201
    assert sent[0]["tier"] == "vision"
    assert len(sent[0]["images"]) == 1
    assert sent[0]["images"][0].base64_data


def test_needs_info_then_resubmit_becomes_approved(
    session: Session, users: dict[str, User], monkeypatch: pytest.MonkeyPatch
) -> None:
    """情報不足 → 補足して再審査 → 公開（完了条件②④）。"""
    install_orca(
        monkeypatch,
        llm_output(
            decision="needs_info",
            score=30,
            missing_info=["撮影してほしい対象を具体的に記載してください"],
        ),
        llm_output(),
    )

    with TestClient(app) as client:
        first = client.post(
            "/api/tasks",
            headers=HEADERS,
            data={**form_data(), "description": "写真撮ってきてください。よろしく。"},
        )
        assert first.status_code == 201
        body = first.json()
        assert body["task"]["status"] == "needs_info"
        assert body["review"]["missingInfo"] == ["撮影してほしい対象を具体的に記載してください"]

        task_id = body["task"]["id"]
        original_location = (
            body["task"]["locationLat"],
            body["task"]["locationLng"],
            body["task"]["locationAddress"],
        )
        second = client.post(
            f"/api/tasks/{task_id}/resubmit",
            headers=HEADERS,
            json={
                "description": "渋谷駅ハチ公口の再開発工事について、正面から工事全景と歩行者の通行状況が分かるように撮影してください。"
            },
        )

    assert second.status_code == 200
    assert second.json()["task"]["status"] == "open"
    assert second.json()["review"]["decision"] == "approved"
    assert (
        second.json()["task"]["locationLat"],
        second.json()["task"]["locationLng"],
        second.json()["task"]["locationAddress"],
    ) == original_location


def test_rejected_task_is_not_published(
    session: Session, users: dict[str, User], monkeypatch: pytest.MonkeyPatch
) -> None:
    """危険な依頼は却下され、掲示板に出ない（完了条件③）。"""
    install_orca(
        monkeypatch,
        llm_output(
            decision="rejected",
            safety="fail",
            score=15,
            rejection_reason="住居の在宅状況の確認は侵入の下見と解釈されるため受け付けられません。",
        ),
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/tasks",
            headers=HEADERS,
            data={
                **form_data(),
                "description": "隣の家に人がいるか確認して写真を撮ってきてください。",
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert body["task"]["status"] == "rejected"
        assert body["review"]["rejectionReason"]

        nearby = client.get(
            "/api/tasks/nearby",
            headers=auth_headers(users["worker"]),
            params={"lat": 35.6595, "lng": 139.7005, "radiusKm": 5},
        )
    assert nearby.json()["tasks"] == []


def test_resubmit_is_rejected_unless_needs_info(
    session: Session, users: dict[str, User], monkeypatch: pytest.MonkeyPatch
) -> None:
    install_orca(monkeypatch, llm_output())

    with TestClient(app) as client:
        created = client.post("/api/tasks", headers=HEADERS, data=form_data())
        task_id = created.json()["task"]["id"]
        response = client.post(
            f"/api/tasks/{task_id}/resubmit",
            headers=HEADERS,
            json={"description": "十分な説明を追記した詳細メッセージです。"},
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATE"


def test_duplicate_task_copies_content_and_changes_only_schedule(
    session: Session, users: dict[str, User], monkeypatch: pytest.MonkeyPatch
) -> None:
    """過去依頼をテンプレートにし、日時だけ変えた独立した依頼を作成できる。"""
    install_orca(monkeypatch, llm_output(), llm_output(summary="複製した依頼です。"))
    now = datetime.now(UTC)
    new_scheduled_at = now + timedelta(days=1)
    new_deadline_at = now + timedelta(days=1, hours=5)

    with TestClient(app) as client:
        created = client.post(
            "/api/tasks",
            headers=HEADERS,
            data=form_data(),
            files=[("referenceImages", ("ref.jpg", reference_image(), "image/jpeg"))],
        )
        source = created.json()["task"]
        response = client.post(
            f"/api/tasks/{source['id']}/duplicate",
            headers=HEADERS,
            json={
                "scheduledAt": new_scheduled_at.isoformat(),
                "deadlineAt": new_deadline_at.isoformat(),
            },
        )

    assert response.status_code == 201
    duplicate = response.json()["task"]
    assert duplicate["id"] != source["id"]
    for field in (
        "title",
        "description",
        "locationLat",
        "locationLng",
        "locationAddress",
        "rewardAmount",
        "requiredWorkerCount",
    ):
        assert duplicate[field] == source[field]
    assert duplicate["scheduledAt"] == new_scheduled_at.isoformat().replace("+00:00", "Z")
    assert duplicate["deadlineAt"] == new_deadline_at.isoformat().replace("+00:00", "Z")
    assert duplicate["status"] == "open"

    tasks = list(session.scalars(select(Task).order_by(Task.created_at)))
    assert len(tasks) == 2
    assert len(tasks[0].reference_images) == 1
    assert len(tasks[1].reference_images) == 1
    assert tasks[1].reference_images[0].image_url == tasks[0].reference_images[0].image_url


def test_duplicate_task_rejects_other_users_task(
    session: Session, users: dict[str, User], monkeypatch: pytest.MonkeyPatch
) -> None:
    install_orca(monkeypatch, llm_output())
    now = datetime.now(UTC)

    with TestClient(app) as client:
        created = client.post("/api/tasks", headers=HEADERS, data=form_data())
        response = client.post(
            f"/api/tasks/{created.json()['task']['id']}/duplicate",
            headers=auth_headers(users["worker"]),
            json={
                "scheduledAt": (now + timedelta(days=1)).isoformat(),
                "deadlineAt": (now + timedelta(days=1, hours=5)).isoformat(),
            },
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_ai_failure_returns_502(
    session: Session, users: dict[str, User], monkeypatch: pytest.MonkeyPatch
) -> None:
    """AI呼び出しが失敗したら 502 AI_SERVICE_ERROR を返す。"""
    settings = get_settings()
    monkeypatch.setattr(settings, "orca_stub_mode", False)
    monkeypatch.setattr(settings, "orca_api_key", "test-key")
    failing = OrcaClient(
        transport=httpx.MockTransport(lambda _request: httpx.Response(401, text="Invalid token"))
    )
    monkeypatch.setattr(tasks_route, "get_orca_client", lambda: failing)

    with TestClient(app) as client:
        response = client.post("/api/tasks", headers=HEADERS, data=form_data())

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "AI_SERVICE_ERROR"


def test_failed_call_is_still_audited(
    session: Session, users: dict[str, User], monkeypatch: pytest.MonkeyPatch
) -> None:
    """AI失敗で依頼はロールバックされても、監査ログは独立して残る（docs/04 1.3）。"""
    from sqlalchemy import func, select

    from app.models import AiInvocation, Task

    settings = get_settings()
    monkeypatch.setattr(settings, "orca_stub_mode", False)
    monkeypatch.setattr(settings, "orca_api_key", "test-key")
    failing = OrcaClient(
        transport=httpx.MockTransport(lambda _request: httpx.Response(401, text="Invalid token"))
    )
    monkeypatch.setattr(tasks_route, "get_orca_client", lambda: failing)

    with TestClient(app) as client:
        assert client.post("/api/tasks", headers=HEADERS, data=form_data()).status_code == 502

    invocation = session.scalars(select(AiInvocation)).one()
    assert invocation.purpose == "task_review"
    assert invocation.error is not None
    assert invocation.model is None
    # 依頼自体は作成されない
    assert session.scalar(select(func.count()).select_from(Task)) == 0
