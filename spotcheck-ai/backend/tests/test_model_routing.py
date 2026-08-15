"""用途ごとのモデル振り分けと、重要な判定の冗長化。

**設計の意図**（docs/04-ai-pipeline.md 1.2）
- 分類軸は「画像の有無」ではなく「間違えたときの損失」
- 同じ入力でもスコアは振れるため、重要な判定は1回の呼び出しに賭けない
"""

from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.services import task_review
from app.services.orca_client import OrcaClient


# ----------------------------------------------------------------------
# 用途別のモデル指定
# ----------------------------------------------------------------------
def test_model_key_overrides_tier_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """用途に指定があれば、tier の既定より優先される。"""
    settings = get_settings()
    monkeypatch.setattr(settings, "orca_router_vision", "orcarouter/auto")
    monkeypatch.setattr(settings, "orca_model_image_validation", "anthropic/claude-opus-5")

    client = OrcaClient()

    assert client.router_name("vision", "image_validation") == "anthropic/claude-opus-5"
    # 指定の無い用途は tier の既定に落ちる
    assert client.router_name("vision", "thumbnail") == "orcarouter/auto"
    # model_key を渡さない従来の呼び方も壊れていない
    assert client.router_name("vision") == "orcarouter/auto"


def test_each_purpose_can_use_a_different_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """検品とサムネイルに別々のモデルを割り当てられる。

    これができないと、中核の検品に合わせて飾りのサムネイルまで
    高価なモデルを使うことになる。
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "orca_model_image_validation", "anthropic/claude-opus-5")
    monkeypatch.setattr(settings, "orca_model_thumbnail", "qwen/qwen3.5-flash")
    monkeypatch.setattr(settings, "orca_model_task_description", "openai/gpt-5-mini")

    client = OrcaClient()

    assert client.router_name("vision", "image_validation") == "anthropic/claude-opus-5"
    assert client.router_name("vision", "thumbnail") == "qwen/qwen3.5-flash"
    assert client.router_name("light", "task_description") == "openai/gpt-5-mini"


def test_masking_can_differ_from_image_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    """マスキングは検品と同じ purpose を使うが、別モデルを割り当てられる。"""
    settings = get_settings()
    monkeypatch.setattr(settings, "orca_model_image_validation", "openai/gpt-5-mini")
    monkeypatch.setattr(settings, "orca_model_masking", "anthropic/claude-opus-5")

    client = OrcaClient()

    assert client.router_name("vision", "image_validation") == "openai/gpt-5-mini"
    assert client.router_name("vision", "masking") == "anthropic/claude-opus-5"


def test_jury_lists_are_split_and_trimmed(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "orca_review_jury", " a/one , b/two ,, ")

    assert settings.orca_review_jury_models == ["a/one", "b/two"]


def test_empty_jury_means_no_redundancy(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "orca_review_jury", "")
    monkeypatch.setattr(settings, "orca_validation_jury", "")

    assert settings.orca_review_jury_models == []
    assert settings.orca_validation_jury_models == []


# ----------------------------------------------------------------------
# 多数決
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    ("votes", "expected"),
    [
        (["approved"], "approved"),
        (["approved", "approved", "rejected"], "approved"),
        (["rejected", "rejected", "approved"], "rejected"),
        (["needs_info", "needs_info", "approved"], "needs_info"),
        # 3者バラバラ → 最も慎重な rejected
        (["approved", "needs_info", "rejected"], "rejected"),
    ],
)
def test_majority_decision(votes: list[str], expected: str) -> None:
    assert task_review.majority_decision(votes) == expected


def test_tie_prefers_the_more_cautious_side() -> None:
    """2モデルで割れたときは慎重な側を採る。

    公開してしまうと取り返しがつかないのに対し、却下・情報補足は
    依頼者が書き直せば済むという非対称性による。
    """
    assert task_review.majority_decision(["approved", "rejected"]) == "rejected"
    assert task_review.majority_decision(["approved", "needs_info"]) == "needs_info"
    assert task_review.majority_decision(["needs_info", "rejected"]) == "rejected"
