"""いいね・保存した検索条件・投稿カードのタグのテスト。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.main import app
from app.models import TaskStatus, User
from app.services import task_card
from tests.conftest import auth_headers, make_task

NEARBY_PARAMS = {"lat": 35.6595, "lng": 139.7005, "radiusKm": 5}


# ----------------------------------------------------------------------
# いいね
# ----------------------------------------------------------------------
def test_like_and_unlike(session: Session, users: dict[str, User]) -> None:
    task = make_task(session, client=users["client"])
    headers = auth_headers(users["worker"])

    with TestClient(app) as api:
        liked = api.post(f"/api/tasks/{task.id}/like", headers=headers)
        listed = api.get("/api/likes", headers=headers)
        unliked = api.delete(f"/api/tasks/{task.id}/like", headers=headers)
        after = api.get("/api/likes", headers=headers)

    assert liked.status_code == 200
    assert liked.json() == {"taskId": str(task.id), "liked": True, "likeCount": 1}
    assert [item["id"] for item in listed.json()["tasks"]] == [str(task.id)]
    assert unliked.json() == {"taskId": str(task.id), "liked": False, "likeCount": 0}
    assert after.json()["tasks"] == []


def test_like_is_idempotent(session: Session, users: dict[str, User]) -> None:
    """二重タップでも件数は増えない。"""
    task = make_task(session, client=users["client"])
    headers = auth_headers(users["worker"])

    with TestClient(app) as api:
        api.post(f"/api/tasks/{task.id}/like", headers=headers)
        second = api.post(f"/api/tasks/{task.id}/like", headers=headers)

    assert second.json()["likeCount"] == 1


def test_unlike_without_like_is_ok(session: Session, users: dict[str, User]) -> None:
    task = make_task(session, client=users["client"])

    with TestClient(app) as api:
        response = api.delete(f"/api/tasks/{task.id}/like", headers=auth_headers(users["worker"]))

    assert response.status_code == 200
    assert response.json()["liked"] is False


def test_cannot_like_own_task(session: Session, users: dict[str, User]) -> None:
    task = make_task(session, client=users["client"])

    with TestClient(app) as api:
        response = api.post(f"/api/tasks/{task.id}/like", headers=auth_headers(users["client"]))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CANNOT_LIKE_OWN_TASK"


def test_like_state_appears_in_lists(session: Session, users: dict[str, User]) -> None:
    """一覧・詳細の両方に自分のいいね状態と件数が入る。"""
    task = make_task(session, client=users["client"])
    headers = auth_headers(users["worker"])

    with TestClient(app) as api:
        api.post(f"/api/tasks/{task.id}/like", headers=headers)
        nearby = api.get("/api/tasks/nearby", headers=headers, params=NEARBY_PARAMS).json()
        detail = api.get(f"/api/tasks/{task.id}", headers=headers).json()
        other = api.get(
            "/api/tasks/nearby", headers=auth_headers(users["worker2"]), params=NEARBY_PARAMS
        ).json()

    assert nearby["tasks"][0]["isLiked"] is True
    assert nearby["tasks"][0]["likeCount"] == 1
    assert detail["isLiked"] is True
    # 他の人から見ると「いいね済み」ではないが件数は見える
    assert other["tasks"][0]["isLiked"] is False
    assert other["tasks"][0]["likeCount"] == 1


def test_liked_list_keeps_completed_tasks(session: Session, users: dict[str, User]) -> None:
    """取引終了した依頼もハート欄には残る（SOLD として表示する）。"""
    task = make_task(session, client=users["client"])
    headers = auth_headers(users["worker"])

    with TestClient(app) as api:
        api.post(f"/api/tasks/{task.id}/like", headers=headers)
        task.status = TaskStatus.COMPLETED
        session.commit()
        listed = api.get("/api/likes", headers=headers).json()

    assert [item["id"] for item in listed["tasks"]] == [str(task.id)]
    assert "sold" in listed["tasks"][0]["badges"]


# ----------------------------------------------------------------------
# 閲覧数とタグ
# ----------------------------------------------------------------------
def test_view_count_increases_for_others_only(session: Session, users: dict[str, User]) -> None:
    task = make_task(session, client=users["client"])

    with TestClient(app) as api:
        api.get(
            f"/api/tasks/{task.id}", headers=auth_headers(users["client"])
        )  # 自分の分は数えない
        api.get(f"/api/tasks/{task.id}", headers=auth_headers(users["worker"]))
        detail = api.get(f"/api/tasks/{task.id}", headers=auth_headers(users["worker2"])).json()

    assert detail["viewCount"] == 2


def test_new_badge_is_given_to_fresh_task(session: Session, users: dict[str, User]) -> None:
    task = make_task(session, client=users["client"])
    assert task_card.build_badges(task) == ["new"]


def test_new_badge_expires(session: Session, users: dict[str, User]) -> None:
    """作成から NEW_TASK_HOURS を過ぎたらタグは消える。"""
    settings = get_settings()
    task = make_task(session, client=users["client"])
    later = datetime.now(UTC) + timedelta(hours=settings.new_task_hours + 1)

    assert task_card.build_badges(task, now=later) == []


def test_hot_badge_uses_view_count(
    session: Session, users: dict[str, User], monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = get_settings()
    task = make_task(session, client=users["client"])
    task.view_count = settings.hot_view_count
    session.commit()

    assert "hot" in task_card.build_badges(task)


def test_sold_badge_replaces_new(session: Session, users: dict[str, User]) -> None:
    """完了済みは SOLD のみ（NEW は付けない）。"""
    task = make_task(session, client=users["client"], status="completed")
    assert task_card.build_badges(task) == ["sold"]


# ----------------------------------------------------------------------
# 保存した検索条件
# ----------------------------------------------------------------------
def test_saved_search_crud(session: Session, users: dict[str, User]) -> None:
    make_task(session, client=users["client"])
    headers = auth_headers(users["worker"])
    payload = {
        "label": "渋谷まわり",
        "centerLat": 35.6595,
        "centerLng": 139.7005,
        "locationAddress": "東京都渋谷区道玄坂1丁目",
        "radiusKm": 5,
        "sort": "distance",
    }

    with TestClient(app) as api:
        created = api.post("/api/saved-searches", headers=headers, json=payload)
        listed = api.get("/api/saved-searches", headers=headers)
        search_id = created.json()["search"]["id"]
        deleted = api.delete(f"/api/saved-searches/{search_id}", headers=headers)
        after = api.get("/api/saved-searches", headers=headers)

    assert created.status_code == 201
    assert created.json()["search"]["label"] == "渋谷まわり"
    # 保存時点で該当した件数が入る
    assert created.json()["search"]["lastMatchCount"] == 1
    assert [item["id"] for item in listed.json()["searches"]] == [search_id]
    assert deleted.status_code == 204
    assert after.json()["searches"] == []


def test_saved_search_label_defaults_to_place(session: Session, users: dict[str, User]) -> None:
    headers = auth_headers(users["worker"])
    payload = {
        "centerLat": 35.6595,
        "centerLng": 139.7005,
        "locationAddress": "東京都渋谷区道玄坂1丁目",
        "radiusKm": 3,
    }

    with TestClient(app) as api:
        created = api.post("/api/saved-searches", headers=headers, json=payload)

    assert created.json()["search"]["label"] == "東京都渋谷区道玄坂1丁目 から3km"


def test_saved_search_is_private(session: Session, users: dict[str, User]) -> None:
    """他人の検索条件は見えないし消せない。"""
    payload = {"centerLat": 35.6595, "centerLng": 139.7005, "radiusKm": 5}

    with TestClient(app) as api:
        created = api.post(
            "/api/saved-searches", headers=auth_headers(users["worker"]), json=payload
        )
        search_id = created.json()["search"]["id"]
        listed_by_other = api.get("/api/saved-searches", headers=auth_headers(users["worker2"]))
        deleted_by_other = api.delete(
            f"/api/saved-searches/{search_id}", headers=auth_headers(users["worker2"])
        )

    assert listed_by_other.json()["searches"] == []
    assert deleted_by_other.status_code == 403


def test_saved_search_requires_login() -> None:
    with TestClient(app) as api:
        assert api.get("/api/saved-searches").status_code == 401
        assert api.get("/api/likes").status_code == 401
