"""1アカウントで「依頼する」「撮影する」を兼ねる場合の振る舞い。

role を廃止したため、権限は「依頼のオーナーか受注者か」で決まる。
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.storage import get_storage
from app.main import app
from app.models import Task, User
from app.services import task_service
from tests.conftest import auth_headers, make_task

NEARBY_PARAMS = {"lat": 35.6595, "lng": 139.7005, "radiusKm": 5}


def test_any_user_can_create_and_accept(session: Session, users: dict[str, User]) -> None:
    """ロールの区別が無いので、依頼を出したことがあるユーザーも他人の依頼を受注できる。"""
    task = make_task(session, client=users["client"])

    with TestClient(app) as api:
        response = api.post(f"/api/tasks/{task.id}/accept", headers=auth_headers(users["worker"]))

    assert response.status_code == 201
    assert response.json()["assignment"]["taskId"] == str(task.id)


def test_owner_cannot_accept_own_task(session: Session, users: dict[str, User]) -> None:
    task = make_task(session, client=users["client"])

    with TestClient(app) as api:
        response = api.post(f"/api/tasks/{task.id}/accept", headers=auth_headers(users["client"]))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CANNOT_ACCEPT_OWN_TASK"


def test_own_task_is_excluded_from_nearby(session: Session, users: dict[str, User]) -> None:
    """自分の依頼は「さがす」に出さない（受注できないため）。"""
    task = make_task(session, client=users["client"])

    with TestClient(app) as api:
        as_owner = api.get(
            "/api/tasks/nearby", headers=auth_headers(users["client"]), params=NEARBY_PARAMS
        )
        as_other = api.get(
            "/api/tasks/nearby", headers=auth_headers(users["worker"]), params=NEARBY_PARAMS
        )

    assert as_owner.json()["tasks"] == []
    assert [item["id"] for item in as_other.json()["tasks"]] == [str(task.id)]


def test_my_tasks_lists_only_own_tasks(session: Session, users: dict[str, User]) -> None:
    mine = make_task(session, client=users["client"])
    make_task(session, client=users["worker"])

    with TestClient(app) as api:
        response = api.get("/api/tasks", headers=auth_headers(users["client"]))

    assert [item["id"] for item in response.json()["tasks"]] == [str(mine.id)]


def test_task_detail_switches_by_ownership(session: Session, users: dict[str, User]) -> None:
    """オーナーにはタイムライン、それ以外には距離と自分の受注状況を返す。"""
    task = make_task(session, client=users["client"])

    with TestClient(app) as api:
        owner_view = api.get(f"/api/tasks/{task.id}", headers=auth_headers(users["client"])).json()
        worker_view = api.get(
            f"/api/tasks/{task.id}",
            headers=auth_headers(users["worker"]),
            params={"lat": 35.6595, "lng": 139.7005},
        ).json()

    assert owner_view["timeline"]
    assert owner_view["myAssignment"] is None
    assert worker_view["timeline"] is None
    assert worker_view["distanceKm"] is not None


def test_other_user_can_view_task_detail(session: Session, users: dict[str, User]) -> None:
    """撮影する側として他人の依頼を見るのは許可される（掲示板から開くため）。"""
    task = make_task(session, client=users["client"])

    with TestClient(app) as api:
        response = api.get(f"/api/tasks/{task.id}", headers=auth_headers(users["worker2"]))

    assert response.status_code == 200


def test_cancel_is_limited_to_owner(session: Session, users: dict[str, User]) -> None:
    task = make_task(session, client=users["client"])

    with TestClient(app) as api:
        by_other = api.post(f"/api/tasks/{task.id}/cancel", headers=auth_headers(users["worker"]))
        by_owner = api.post(f"/api/tasks/{task.id}/cancel", headers=auth_headers(users["client"]))

    assert by_other.status_code == 403
    assert by_owner.status_code == 200
    assert by_owner.json()["task"]["status"] == "cancelled"


def test_results_are_limited_to_owner(session: Session, users: dict[str, User]) -> None:
    task = make_task(session, client=users["client"])

    with TestClient(app) as api:
        response = api.get(f"/api/tasks/{task.id}/results", headers=auth_headers(users["worker"]))

    assert response.status_code == 403


async def test_find_nearby_excludes_viewer_tasks(session: Session, users: dict[str, User]) -> None:
    """サービス層でも閲覧者による除外が効いている。"""
    make_task(session, client=users["client"])
    other: Task = make_task(session, client=users["worker"])

    found = await task_service.find_nearby(
        session,
        viewer=users["client"],
        storage=get_storage(),
        lat=35.6595,
        lng=139.7005,
        radius_km=5,
        limit=50,
        sort="distance",
    )

    assert [item.id for item in found] == [other.id]
