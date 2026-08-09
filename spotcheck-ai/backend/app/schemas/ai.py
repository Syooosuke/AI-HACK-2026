"""AIの出力スキーマ（docs/04-ai-pipeline.md 2.2, 3.1）。

`OrcaClient` はこれらのモデルで応答をバリデートする。スタブ応答も同じ形に従う。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.submission import IssueCode


class IssueItem(BaseModel):
    code: IssueCode
    #: 画面⑧に表示する日本語の再撮影指示
    message: str


class TaskReviewResult(BaseModel):
    """機能A: 依頼コンテキスト審査の出力。"""

    decision: Literal["approved", "needs_info", "rejected"]
    #: 情報の十分性 0-100
    score: int
    safety: Literal["pass", "fail"]
    validity: Literal["pass", "fail"]
    risk: Literal["pass", "fail"]
    duplication: Literal["pass", "fail"]
    rejection_reason: str | None = None
    missing_info: list[str] = Field(default_factory=list)
    summary: str


class ImageValidationResult(BaseModel):
    """機能B: VLMによる画像検品の出力。"""

    score: int
    subject_present: bool
    framing_ok: bool
    sharpness_ok: bool
    brightness_ok: bool
    reference_match: bool | None = None
    #: 画像に写っているものの客観的記述（機能C の環境整合で使用）
    observed_scene: str = ""
    daylight_state: Literal["daylight", "twilight", "night", "indoor", "unknown"] = "unknown"
    weather_hint: Literal["clear", "cloudy", "rain", "snow", "unknown"] = "unknown"
    issues: list[IssueItem] = Field(default_factory=list)
    summary: str = ""


class PrivacyRegion(BaseModel):
    """VLM が返すプライバシー領域（docs/04-ai-pipeline.md 5.2）。座標は 0.0〜1.0 の正規化座標。"""

    kind: Literal["license_plate", "nameplate", "address_sign", "personal_document"]
    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float = 1.0


class PrivacyRegionList(BaseModel):
    regions: list[PrivacyRegion] = Field(default_factory=list)


class ResultSummaryResult(BaseModel):
    """機能: クライアント向けの結果要約。"""

    summary: str
