"""認証（新規登録・ログイン・トークン検証）のテスト。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.main import app
from app.models import User
from tests.conftest import TEST_PASSWORD, auth_headers

SIGNUP_PAYLOAD = {
    "loginId": "new_user",
    "password": "very-secret-1",
    "displayName": "新規 ユーザー",
}


# ----------------------------------------------------------------------
# 新規登録
# ----------------------------------------------------------------------
def test_signup_returns_token_and_user() -> None:
    with TestClient(app) as client:
        response = client.post("/api/auth/signup", json=SIGNUP_PAYLOAD)

    assert response.status_code == 201
    body = response.json()
    assert body["tokenType"] == "Bearer"
    assert body["expiresIn"] > 0
    assert body["user"]["loginId"] == "new_user"
    assert body["user"]["displayName"] == "新規 ユーザー"
    # パスワード関連の値は絶対に返さない
    assert "passwordHash" not in body["user"]
    assert "password" not in response.text


def test_signup_token_is_usable() -> None:
    with TestClient(app) as client:
        token = client.post("/api/auth/signup", json=SIGNUP_PAYLOAD).json()["token"]
        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert me.status_code == 200
    assert me.json()["user"]["loginId"] == "new_user"


def test_signup_stores_hashed_password(session: Session) -> None:
    with TestClient(app) as client:
        user_id = client.post("/api/auth/signup", json=SIGNUP_PAYLOAD).json()["user"]["id"]

    user = session.get(User, uuid.UUID(user_id))
    assert user is not None
    assert user.password_hash != SIGNUP_PAYLOAD["password"]
    assert verify_password(SIGNUP_PAYLOAD["password"], user.password_hash)


def test_signup_rejects_duplicated_login_id(users: dict[str, User]) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/auth/signup",
            json={**SIGNUP_PAYLOAD, "loginId": users["client"].login_id},
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "LOGIN_ID_TAKEN"


def test_signup_rejects_short_password() -> None:
    with TestClient(app) as client:
        response = client.post("/api/auth/signup", json={**SIGNUP_PAYLOAD, "password": "short1"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_signup_rejects_invalid_login_id() -> None:
    """ログインIDは半角英数字とアンダースコアのみ。"""
    with TestClient(app) as client:
        response = client.post("/api/auth/signup", json={**SIGNUP_PAYLOAD, "loginId": "ユーザー"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


# ----------------------------------------------------------------------
# ログイン
# ----------------------------------------------------------------------
def test_login_succeeds_with_correct_password(users: dict[str, User]) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/auth/login",
            json={"loginId": users["worker"].login_id, "password": TEST_PASSWORD},
        )

    assert response.status_code == 200
    assert response.json()["user"]["id"] == str(users["worker"].id)


def test_login_is_case_insensitive_for_login_id(users: dict[str, User]) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/auth/login",
            json={"loginId": users["worker"].login_id.upper(), "password": TEST_PASSWORD},
        )

    assert response.status_code == 200


def test_login_rejects_wrong_password(users: dict[str, User]) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/auth/login",
            json={"loginId": users["worker"].login_id, "password": "wrong-password"},
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_login_rejects_unknown_login_id(users: dict[str, User]) -> None:
    """存在しないIDでも、パスワード誤りと同じ応答にする（IDの存在を推測させない）。"""
    with TestClient(app) as client:
        unknown = client.post(
            "/api/auth/login", json={"loginId": "no_such_user", "password": TEST_PASSWORD}
        )
        wrong = client.post(
            "/api/auth/login",
            json={"loginId": users["worker"].login_id, "password": "wrong-password"},
        )

    assert unknown.status_code == 401
    assert unknown.json() == wrong.json()


def test_login_rejects_unusable_password_hash(session: Session) -> None:
    """マイグレーションで入る `!` のままではログインできない。"""
    session.add(User(login_id="legacy_user", password_hash="!", display_name="移行前のユーザー"))
    session.commit()

    with TestClient(app) as client:
        response = client.post("/api/auth/login", json={"loginId": "legacy_user", "password": "!"})

    assert response.status_code == 401


# ----------------------------------------------------------------------
# トークン検証
# ----------------------------------------------------------------------
def test_me_requires_token(users: dict[str, User]) -> None:
    with TestClient(app) as client:
        response = client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_me_rejects_non_bearer_scheme(users: dict[str, User]) -> None:
    with TestClient(app) as client:
        response = client.get("/api/auth/me", headers={"Authorization": "Basic abcdef"})

    assert response.status_code == 401


def test_me_rejects_broken_token() -> None:
    with TestClient(app) as client:
        response = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-jwt"})

    assert response.status_code == 401


def test_me_rejects_expired_token(users: dict[str, User]) -> None:
    expired = create_access_token(users["worker"].id, now=datetime.now(UTC) - timedelta(days=365))
    with TestClient(app) as client:
        response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired}"})

    assert response.status_code == 401


def test_me_rejects_token_of_deleted_user() -> None:
    """トークンは正しいが、そのユーザーが存在しない場合も 401。"""
    with TestClient(app) as client:
        response = client.get("/api/auth/me", headers=auth_headers(uuid.uuid4()))

    assert response.status_code == 401


def test_protected_endpoint_requires_token(users: dict[str, User]) -> None:
    """業務APIも同じ仕組みで保護されている。"""
    with TestClient(app) as client:
        assert client.get("/api/tasks").status_code == 401
        assert client.get("/api/tasks", headers=auth_headers(users["client"])).status_code == 200


# ----------------------------------------------------------------------
# パスワードハッシュ
# ----------------------------------------------------------------------
def test_password_hash_is_salted() -> None:
    """同じパスワードでもハッシュは毎回変わる（ソルトが効いている）。"""
    first = hash_password("same-password")
    second = hash_password("same-password")
    assert first != second
    assert verify_password("same-password", first)
    assert verify_password("same-password", second)


def test_verify_password_rejects_broken_hash() -> None:
    assert verify_password("whatever", "not-a-bcrypt-hash") is False
