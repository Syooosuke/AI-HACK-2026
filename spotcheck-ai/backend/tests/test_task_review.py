"""依頼審査（機能A）のテスト（docs/04-ai-pipeline.md 2節）。

**LLMの decision をそのまま信用せず、サーバー側が最終決定する**ことを検証する。
モデルの判断そのもの（危険な依頼を fail にできるか）は実APIでの確認が必要。
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import TaskStatus, User
from app.prompts.task_review import build_user_prompt
from app.schemas.ai import TaskReviewResult
from app.services import task_review
from app.services.orca_client import OrcaClient
from tests.conftest import make_task


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


def envelope(content: str) -> dict[str, Any]:
    return {
        "id": "chatcmpl-test",
        "model": "grok/grok-4.5",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
    }


@pytest.fixture(autouse=True)
def live_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "orca_stub_mode", False)
    monkeypatch.setattr(settings, "orca_api_key", "test-key")


def client_returning(*contents: str) -> OrcaClient:
    """呼び出し回数に応じて応答を切り替えるクライアント。"""
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        index = min(calls["n"], len(contents) - 1)
        calls["n"] += 1
        return httpx.Response(200, json=envelope(contents[index]))

    return OrcaClient(transport=httpx.MockTransport(handler))


# ----------------------------------------------------------------------
# 判定ロジック（docs/04-ai-pipeline.md 2.3）
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({}, "approved"),
        ({"safety": "fail"}, "rejected"),
        ({"risk": "fail"}, "rejected"),
        ({"validity": "fail"}, "needs_info"),
        ({"score": 69}, "needs_info"),
        ({"score": 70}, "approved"),
        # duplication は判定に用いない（表示のみ）
        ({"duplication": "fail"}, "approved"),
        # safety が fail なら score が高くても却下
        ({"safety": "fail", "score": 100}, "rejected"),
    ],
)
def test_decide(overrides: dict[str, Any], expected: str) -> None:
    result = TaskReviewResult.model_validate(json.loads(llm_output(**overrides)))
    assert task_review.decide(result, score_threshold=70) == expected


def test_server_overrides_llm_decision() -> None:
    """LLM が approved と言っても、safety=fail ならサーバー側で rejected にする。"""
    result = TaskReviewResult.model_validate(
        json.loads(llm_output(decision="approved", safety="fail"))
    )
    assert task_review.decide(result, score_threshold=70) == "rejected"


# ----------------------------------------------------------------------
# review_task による tasks の更新
# ----------------------------------------------------------------------
async def test_approved_task_is_published(session: Session, users: dict[str, User]) -> None:
    task = make_task(session, client=users["client"], status="screening")
    outcome = await task_review.review_task(session, task, client_returning(llm_output()))
    session.flush()

    assert outcome.review.decision == "approved"
    assert task.status is TaskStatus.OPEN
    assert task.review_score == 85
    assert task.review_summary == "駅前の工事の進捗を確認する依頼です。"
    assert task.review_feedback["checks"]["safety"] == "pass"
    assert task.review_feedback["missingInfo"] == []


async def test_insufficient_task_requests_more_info(
    session: Session, users: dict[str, User]
) -> None:
    task = make_task(session, client=users["client"], status="screening")
    outcome = await task_review.review_task(
        session,
        task,
        client_returning(
            llm_output(
                decision="needs_info",
                score=35,
                missing_info=[
                    "撮影してほしい対象を具体的に記載してください",
                    "撮影してほしいアングル（正面／側面）を指定してください",
                ],
            )
        ),
    )

    assert outcome.review.decision == "needs_info"
    assert task.status is TaskStatus.NEEDS_INFO
    assert len(outcome.review.missing_info) == 2
    assert task.review_feedback["missingInfo"] == outcome.review.missing_info


async def test_unsafe_task_is_rejected(session: Session, users: dict[str, User]) -> None:
    task = make_task(session, client=users["client"], status="screening")
    outcome = await task_review.review_task(
        session,
        task,
        client_returning(
            llm_output(
                decision="rejected",
                safety="fail",
                score=20,
                rejection_reason="住居の在宅状況の確認は侵入の下見と解釈されるため受け付けられません。",
            )
        ),
    )

    assert outcome.review.decision == "rejected"
    assert task.status is TaskStatus.REJECTED
    assert outcome.review.rejection_reason is not None
    assert task.review_feedback["rejectionReason"] == outcome.review.rejection_reason
    # 却下時は補足要求を出さない
    assert outcome.review.missing_info == []


async def test_resubmitted_task_can_become_approved(
    session: Session, users: dict[str, User]
) -> None:
    """needs_info → 補足して再審査 → approved（完了条件④）。"""
    task = make_task(session, client=users["client"], status="screening")
    orca = client_returning(llm_output(decision="needs_info", score=40), llm_output())

    first = await task_review.review_task(session, task, orca)
    assert first.review.decision == "needs_info"
    assert task.status is TaskStatus.NEEDS_INFO

    task.description = task.description + " 正面から全景が入るように撮影してください。"
    task.status = TaskStatus.SCREENING
    second = await task_review.review_task(session, task, orca)

    assert second.review.decision == "approved"
    assert task.status is TaskStatus.OPEN


async def test_invocation_is_logged(session: Session, users: dict[str, User]) -> None:
    from sqlalchemy import select

    from app.models import AiInvocation

    task = make_task(session, client=users["client"], status="screening")
    await task_review.review_task(session, task, client_returning(llm_output()))
    session.flush()

    invocation = session.scalars(select(AiInvocation)).one()
    assert invocation.purpose == "task_review"
    assert invocation.related_type == "task"
    assert invocation.related_id == task.id
    assert invocation.model == "grok/grok-4.5"
    assert invocation.is_stub is False
    assert invocation.error is None


async def test_stub_mode_still_works(
    session: Session, users: dict[str, User], monkeypatch: pytest.MonkeyPatch
) -> None:
    """ORCA_STUB_MODE=true に戻すとスタブで動作する（完了条件⑤）。"""
    monkeypatch.setattr(get_settings(), "orca_stub_mode", True)
    task = make_task(session, client=users["client"], status="screening")

    def explode(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("スタブモードでHTTPを呼んではいけない")

    outcome = await task_review.review_task(
        session, task, OrcaClient(transport=httpx.MockTransport(explode))
    )

    assert outcome.review.decision == "approved"
    assert outcome.review.score == 85
    assert task.status is TaskStatus.OPEN


# ----------------------------------------------------------------------
# プロンプト
# ----------------------------------------------------------------------
def test_user_prompt_contains_task_details(session: Session, users: dict[str, User]) -> None:
    task = make_task(session, client=users["client"])
    prompt = build_user_prompt(task, has_reference_images=False)

    assert task.title in prompt
    assert task.description in prompt
    assert str(task.location_lat) in prompt
    assert "住所 東京都渋谷区道玄坂1丁目" in prompt
    assert "【参考画像】なし" in prompt
    assert "日本時間" in prompt
    assert prompt.rstrip().endswith("JSONのみを出力してください。")


def test_user_prompt_mentions_reference_images(session: Session, users: dict[str, User]) -> None:
    task = make_task(session, client=users["client"])
    prompt = build_user_prompt(task, has_reference_images=True)

    assert "【参考画像】あり" in prompt
    assert "参考画像に写っている被写体が依頼内容と一致しているかも確認してください。" in prompt
