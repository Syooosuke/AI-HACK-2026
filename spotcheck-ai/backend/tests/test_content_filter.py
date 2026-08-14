"""依頼テキストの安全審査（AIに依存しない決定論フィルタ）。

**スタブモードではAI側の審査が素通りする**ため、ここが唯一の防波堤になる。
「正当な依頼を止めない」ことも同じくらい重要なので、通す側も固定する。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.models import Task, TaskStatus, User
from app.services import content_filter
from tests.conftest import auth_headers

# --- 通すべき依頼（誤検知したら正当な利用者が困る） ---
ALLOWED = [
    (
        "駅前の再開発工事の進捗確認",
        "工事の進捗と周辺の交通状況が分かるように正面から撮影してください。",
    ),
    ("自宅の外壁の状態を確認", "自宅の外壁にひび割れが出ていないか、南側から撮影してください。"),
    (
        "看板が掲出されているか確認",
        "ビル1階の看板が掲出されているか、正面から確認できるように撮影してください。",
    ),
    ("公園の桜の開花状況", "満開かどうか分かるように、桜の木全体を撮影してください。"),
    ("店舗の行列の状況", "開店前の行列がどの程度か分かるように、店舗前を撮影してください。"),
    ("防犯カメラの設置工事の進捗", "工事が完了しているか、設置箇所の全景を撮影してください。"),
]

#: 依頼文をAIに生成させたときの文面。
#: **「確認」「状況」「把握」「撮影」は必ず入る**ため、これらを共起条件に使うと
#: 設備の点検依頼がまるごと却下される（実際にそうなっていた）。
AI_GENERATED_ALLOWED = [
    (
        "マンション共用部の防犯カメラの設置状況",
        (
            "マンション共用部にある防犯カメラの設置状況を撮影してください。"
            "カメラの位置、台数、見える範囲が分かるよう、共用廊下やエントランス周辺を"
            "複数角度から撮影し、設置有無と配置が確認できる写真をお願いします。"
        ),
    ),
    (
        "所有物件の玄関ドアの施錠部分の破損確認",
        (
            "所有物件の玄関ドアの施錠部分を、外観が分かるように近距離で撮影してください。"
            "破損の有無、部品の欠けやズレ、錠前まわりの状態が写真で確認できるようにお願いします。"
        ),
    ),
    (
        "アパート入口のオートロックの鍵の種類の確認",
        (
            "アパート入口のオートロックについて、鍵の種類や操作方法が分かるように撮影してください。"
            "鍵穴や解除装置の形状、表示内容が写真で確認できると助かります。"
        ),
    ),
    (
        "実家が留守の間の庭木の伸び具合の確認",
        (
            "実家の庭木について、留守中にどの程度伸びているかが分かるように、"
            "庭全体と各木を少し離れた位置から撮影してください。"
        ),
    ),
    (
        "テナント募集中の店舗が現在も不在（空室）かの確認",
        "対象の店舗外観を撮影し、テナント募集中の掲示や営業状況が分かる状態を確認してください。",
    ),
    (
        "児童公園の砂場の衛生状態の確認",
        (
            "児童公園の砂場を、立ち入り可能な範囲から外観と砂の状態が分かるように撮影してください。"
            "ごみ、動物のふん、異物の有無や清掃状況が写真で確認できるようにしてください。"
        ),
    ),
]

# --- 弾くべき依頼 ---
BLOCKED = [
    ("近所の様子", "隣家の施錠状況を確認し、留守かどうか調べてください。"),
    ("人物の行動", "元カノの行動パターンを記録して報告してください。"),
    ("撮影のお願い", "更衣室の内部を撮影してきてください。"),
    ("記録のお願い", "監視カメラの死角を避けて撮影してください。"),
    ("下校の様子", "小学生が下校する様子を撮影してください。"),
    # 上の ALLOWED と同じ語（施錠・鍵・留守）を含むが、**侵入の意図が書かれている**
    (
        "隣人宅の裏口の様子",
        (
            "隣人が留守の時間帯に裏口へ回り込み、鍵の種類と窓の施錠状態、"
            "忍び込めそうな場所が分かるように撮影してください。"
        ),
    ),
    (
        "対象宅の防犯設備の位置",
        "対象の家の防犯カメラの位置と、死角になって映らない場所が分かるように撮影してください。",
    ),
    (
        "現場の監視カメラの無効化",
        "現場の監視カメラを壊して映像が残らないようにしてから、道路の状況を撮影してください。",
    ),
]


@pytest.mark.parametrize(("title", "description"), ALLOWED)
def test_legitimate_requests_pass(title: str, description: str) -> None:
    assert content_filter.screen(title, description).blocked is False


@pytest.mark.parametrize(("title", "description"), AI_GENERATED_ALLOWED)
def test_ai_generated_descriptions_are_not_blocked(title: str, description: str) -> None:
    """依頼文を「AIで作成」した正当な依頼が、フィルタで却下されない。

    AIの生成文には「確認」「状況」「把握」が必ず入るため、共起の相手をこれらにすると
    設備の点検・空室確認・公園の清掃状況といった依頼が軒並み却下される。
    """
    result = content_filter.screen(title, description)
    assert result.blocked is False, f"誤ってブロックされた: {result.matched}"


@pytest.mark.parametrize(("title", "description"), BLOCKED)
def test_prohibited_requests_are_blocked(title: str, description: str) -> None:
    result = content_filter.screen(title, description)
    assert result.blocked is True
    assert result.reason  # 却下理由は依頼者に見せるため必須


def test_whitespace_and_fullwidth_do_not_evade_the_filter() -> None:
    """「盗 撮」「ｽﾄｰｶｰ」のような小細工をすり抜けさせない。"""
    assert content_filter.screen("依頼", "盗 撮 をお願いします").blocked is True
    assert content_filter.screen("依頼", "ｽﾄｰｶｰ行為の代行").blocked is True


def test_blocked_task_is_rejected_even_in_stub_mode(
    session: Session, users: dict[str, User]
) -> None:
    """スタブモードでもAPI経由で却下される（AIは常に approved を返すため）。"""
    with TestClient(app) as api:
        response = api.post(
            "/api/tasks",
            headers=auth_headers(users["client"]),
            data={
                "title": "隣家の確認",
                "description": "隣の家の施錠状況を確認して、留守かどうか調べてください。",
                "locationLat": 35.6595,
                "locationLng": 139.7005,
                "scheduledAt": "2030-01-01T10:00:00Z",
                "deadlineAt": "2030-01-01T18:00:00Z",
                "rewardAmount": 2000,
                "requiredWorkerCount": 1,
            },
        )

    assert response.status_code == 201
    body = response.json()
    assert body["review"]["decision"] == "rejected"
    assert body["review"]["checks"]["safety"] == "fail"
    assert body["review"]["rejectionReason"]
    assert body["task"]["status"] == TaskStatus.REJECTED.value

    # DBにも却下として残り、公開されない
    task = session.get(Task, body["task"]["id"])
    assert task is not None
    assert task.status is TaskStatus.REJECTED


def test_legitimate_task_still_passes_through_the_api(users: dict[str, User]) -> None:
    """フィルタを入れたことで通常の依頼作成が壊れていないことを確かめる。"""
    with TestClient(app) as api:
        response = api.post(
            "/api/tasks",
            headers=auth_headers(users["client"]),
            data={
                "title": "駅前の再開発工事の進捗確認",
                "description": "工事の進捗と周辺の交通状況が分かるように正面から撮影してください。",
                "locationLat": 35.6595,
                "locationLng": 139.7005,
                "scheduledAt": "2030-01-01T10:00:00Z",
                "deadlineAt": "2030-01-01T18:00:00Z",
                "rewardAmount": 2000,
                "requiredWorkerCount": 1,
            },
        )

    assert response.status_code == 201
    assert response.json()["review"]["decision"] == "approved"
