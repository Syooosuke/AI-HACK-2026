"""検品の境界再判定。

**なぜ必要か**: 同じ画像・同じプロンプト・temperature 0.2 でも、スコアが
30 と 95 のように合否をまたいで振れることを実測した。ただし振れるのは
しきい値付近だけで、明らかな合格・不合格は安定していた。
そこで境界に入ったときだけ追加で判定させ、多数決で決める。
"""

from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.schemas.ai import ImageValidationResult
from app.services import image_validation
from app.services.orca_client import OrcaResult


def _result(score: int) -> OrcaResult:
    parsed = ImageValidationResult(
        score=score,
        subject_present=True,
        framing_ok=True,
        sharpness_ok=True,
        brightness_ok=True,
        reference_match=None,
        observed_scene="駅の改札周辺",
        daylight_state="daylight",
        weather_hint="clear",
        issues=[],
        summary="対象を確認しました。",
    )
    return OrcaResult(parsed=parsed, raw={}, model="test", latency_ms=1, is_stub=False)


async def _resolve(first: int, extra: list[int], *, jury: list[str], monkeypatch):
    """`_resolve_boundary` を、追加判定の戻り値を固定して呼ぶ。"""
    settings = get_settings()
    monkeypatch.setattr(settings, "orca_validation_jury", ",".join(jury))
    monkeypatch.setattr(settings, "submission_score_threshold", 70)
    monkeypatch.setattr(settings, "orca_validation_boundary", 15)

    calls: list[str | None] = []
    queue = list(extra)

    async def ask(model: str | None) -> OrcaResult:
        calls.append(model)
        return _result(queue.pop(0))

    import uuid

    out = await image_validation._resolve_boundary(
        _result(first), ask=ask, submission_id=uuid.uuid4(), settings=settings
    )
    return out.parsed.score, calls  # type: ignore[union-attr]


# ----------------------------------------------------------------------
# 追加判定を「しない」ケース
# ----------------------------------------------------------------------
@pytest.mark.anyio
async def test_clear_pass_is_not_re_judged(monkeypatch: pytest.MonkeyPatch) -> None:
    """明らかな合格（95）では追加の呼び出しをしない。待ち時間を増やさないため。"""
    score, calls = await _resolve(95, [], jury=["m/one", "m/two"], monkeypatch=monkeypatch)

    assert score == 95
    assert calls == []


@pytest.mark.anyio
async def test_clear_fail_is_not_re_judged(monkeypatch: pytest.MonkeyPatch) -> None:
    score, calls = await _resolve(10, [], jury=["m/one", "m/two"], monkeypatch=monkeypatch)

    assert score == 10
    assert calls == []


@pytest.mark.anyio
async def test_no_jury_means_single_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """合議モデルが未設定なら、境界でも1回だけで決める（従来どおり）。"""
    score, calls = await _resolve(72, [], jury=[], monkeypatch=monkeypatch)

    assert score == 72
    assert calls == []


# ----------------------------------------------------------------------
# 追加判定を「する」ケース
# ----------------------------------------------------------------------
@pytest.mark.anyio
async def test_boundary_pass_upheld_by_majority(monkeypatch: pytest.MonkeyPatch) -> None:
    """境界の合格（72）で、追加2件も合格なら合格のまま。"""
    score, calls = await _resolve(72, [80, 75], jury=["m/one", "m/two"], monkeypatch=monkeypatch)

    assert calls == ["m/one", "m/two"]
    assert score >= 70


@pytest.mark.anyio
async def test_boundary_pass_overturned_by_majority(monkeypatch: pytest.MonkeyPatch) -> None:
    """境界の合格（72）でも、追加2件が不合格なら**不合格へ覆る**。

    1回目の結果をそのまま採るのではなく、多数決で決めることの確認。
    """
    score, calls = await _resolve(72, [30, 40], jury=["m/one", "m/two"], monkeypatch=monkeypatch)

    assert calls == ["m/one", "m/two"]
    assert score < 70


@pytest.mark.anyio
async def test_boundary_fail_overturned_by_majority(monkeypatch: pytest.MonkeyPatch) -> None:
    """境界の不合格（65）でも、追加2件が合格なら合格へ覆る。

    不当な不合格は現地へ行ったワーカーの労力を無にし、再撮影枠も消費する。
    """
    score, calls = await _resolve(65, [85, 90], jury=["m/one", "m/two"], monkeypatch=monkeypatch)

    assert calls == ["m/one", "m/two"]
    assert score >= 70


@pytest.mark.anyio
async def test_failed_extra_call_does_not_break_the_verdict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """追加判定が落ちても、残った票で決める（検品全体は止めない）。"""
    settings = get_settings()
    monkeypatch.setattr(settings, "orca_validation_jury", "m/one,m/two")
    monkeypatch.setattr(settings, "submission_score_threshold", 70)
    monkeypatch.setattr(settings, "orca_validation_boundary", 15)

    async def ask(model: str | None) -> OrcaResult:
        if model == "m/one":
            raise RuntimeError("upstream error")
        return _result(90)

    import uuid

    out = await image_validation._resolve_boundary(
        _result(72), ask=ask, submission_id=uuid.uuid4(), settings=settings
    )

    # 72（合格）と 90（合格）の2票で合格
    assert out.parsed.score >= 70  # type: ignore[union-attr]
