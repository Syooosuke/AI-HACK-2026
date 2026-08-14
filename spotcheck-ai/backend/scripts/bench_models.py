"""検品プロンプトのモデル比較（実AIを叩く回帰テスト）。

**なぜ必要か**

モデルは予告なく差し替わり、プロンプトも改善のたびに変わる。
どちらも「気づいたら検品精度が落ちていた」を招くが、通常のテストでは検出できない
（スタブしか通らないため）。モデルやプロンプトを変えるときは必ずこれを流す。

    ORCA_API_KEY=... python -m scripts.bench_models
    ORCA_API_KEY=... python -m scripts.bench_models --models anthropic/claude-opus-5,openai/gpt-5-mini

**CIには入れない。** 実際に課金が発生し、外部サービスの状態に左右されるため。

判定の材料は3つ。
1. 正答率 — 模範解答と一致するか
2. 安定性 — 同じ入力で2回とも同じ合否になるか（割れると再撮影指示が理不尽になる）
3. 所要時間 — ワーカーは現地で待っている
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import io
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageEnhance

from app.core.config import get_settings
from app.prompts import image_validation as iv

#: 既定で比べるモデル。実測で上位だったものと、現状の既定を並べる
DEFAULT_MODELS = (
    "anthropic/claude-opus-5",
    "google/gemini-3.1-pro-preview",
    "openai/gpt-5-mini",
    "orcarouter/auto",
)
RUNS = 2
FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "bench"


# ----------------------------------------------------------------------
# プロンプトへ渡す最小限のダミー（DBに触らずに実プロンプトを組み立てる）
# ----------------------------------------------------------------------
@dataclass
class _Task:
    title: str
    description: str
    location_address: str = "東京都渋谷区道玄坂1丁目"
    location_lat: float = 35.6595
    location_lng: float = 139.7005
    scheduled_at: datetime = datetime(2026, 1, 1, 12, tzinfo=UTC)


@dataclass
class _Submission:
    captured_at: datetime
    attempt_no: int = 1


@dataclass
class Case:
    label: str
    task: _Task
    submission: _Submission
    image_name: str
    #: 期待する被写体の有無と合否
    subject_present: bool
    should_pass: bool
    #: 画像を暗くするか（夜間撮影の再現）
    darken: bool = False


def _placeholder(text: str) -> Image.Image:
    """画像素材が無い環境でも動くようにする代替画像。"""
    im = Image.new("RGB", (640, 480), (210, 214, 220))
    ImageDraw.Draw(im).text((20, 220), text, fill=(60, 64, 70))
    return im


def load_image(name: str, *, darken: bool) -> str:
    path = FIXTURES / name
    image = Image.open(path) if path.exists() else _placeholder(name)
    if darken:
        image = ImageEnhance.Brightness(image).enhance(0.3)
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=88)
    return base64.b64encode(buffer.getvalue()).decode()


NIGHT = datetime(2026, 1, 1, 21, tzinfo=UTC) - timedelta(hours=9)
NOON = datetime(2026, 1, 1, 12, tzinfo=UTC) - timedelta(hours=9)

CASES = (
    Case(
        "①一致・駅の改札",
        _Task(
            "駅の改札周辺の様子", "駅の改札周辺の様子が分かるように、通路全体を撮影してください。"
        ),
        _Submission(NOON),
        "station.jpg",
        subject_present=True,
        should_pass=True,
    ),
    Case(
        "②不一致・工事現場を要求",
        _Task(
            "駅前の再開発工事の進捗",
            "工事現場の全景と、足場の設置状況が分かるように撮影してください。",
        ),
        _Submission(NOON),
        "station.jpg",
        subject_present=False,
        should_pass=False,
    ),
    Case(
        "③一致・夜間で暗い",
        _Task(
            "駅の改札周辺の様子", "駅の改札周辺の様子が分かるように、通路全体を撮影してください。"
        ),
        _Submission(NIGHT),
        "station.jpg",
        subject_present=True,
        should_pass=True,
        darken=True,
    ),
    Case(
        "④一致・道路の交通状況",
        _Task(
            "道路の交通状況の確認", "車線の混み具合とバスの停車状況が分かるように撮影してください。"
        ),
        _Submission(NOON),
        "road.jpg",
        subject_present=True,
        should_pass=True,
    ),
    Case(
        "⑤不一致・店舗の行列を要求",
        _Task("店舗前の行列の状況", "開店前に何人ぐらい並んでいるか分かるように撮影してください。"),
        _Submission(NOON),
        "road.jpg",
        subject_present=False,
        should_pass=False,
    ),
)


async def ask(client: httpx.AsyncClient, model: str, case: Case, image: str) -> dict:
    settings = get_settings()
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": iv.SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": iv.build_user_prompt(
                            case.task, case.submission, has_reference=False
                        ),
                    },
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image}"}},
                ],
            },
        ],
        "temperature": 0.2,
        "max_tokens": 4000,
    }
    started = time.perf_counter()
    try:
        response = await client.post(
            f"{settings.orca_api_base_url.rstrip('/')}/chat/completions",
            json=body,
            headers={"Authorization": f"Bearer {settings.orca_api_key}"},
            timeout=300,
        )
    except Exception as exc:  # noqa: BLE001 - 1件の失敗で全体を止めない
        return {"error": type(exc).__name__, "seconds": time.perf_counter() - started}

    seconds = time.perf_counter() - started
    if response.status_code >= 300:
        return {"error": f"HTTP{response.status_code}", "seconds": seconds}
    text = ((response.json().get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return {"parsed": json.loads(text), "seconds": seconds}
    except json.JSONDecodeError:
        return {"error": "JSON解析失敗", "seconds": seconds}


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", help="比較するモデル（カンマ区切り）")
    args = parser.parse_args()
    models = [m.strip() for m in args.models.split(",")] if args.models else list(DEFAULT_MODELS)

    settings = get_settings()
    if not settings.orca_api_key:
        raise SystemExit("ORCA_API_KEY が未設定です。実AIを叩くため必須です。")

    threshold = settings.submission_score_threshold
    images = {
        c.image_name + str(c.darken): load_image(c.image_name, darken=c.darken) for c in CASES
    }

    semaphore = asyncio.Semaphore(8)
    results: dict[tuple[str, str, int], dict] = {}

    async with httpx.AsyncClient() as client:

        async def one(model: str, case: Case, run: int) -> None:
            async with semaphore:
                results[(model, case.label, run)] = await ask(
                    client, model, case, images[case.image_name + str(case.darken)]
                )

        jobs = [one(m, c, r) for m in models for c in CASES for r in range(RUNS)]
        print(f"実AIへ {len(jobs)} 回問い合わせます（しきい値 score>={threshold}）\n")
        await asyncio.gather(*jobs)

    print(f"{'モデル':<34}{'正答':>7}{'ブレ':>7}{'エラー':>7}{'平均秒':>9}")
    print("-" * 66)
    rows = []
    for model in models:
        correct = unstable = errors = 0
        seconds: list[float] = []
        for case in CASES:
            runs = [results[(model, case.label, r)] for r in range(RUNS)]
            if any("error" in r for r in runs):
                errors += 1
                continue
            seconds += [r["seconds"] for r in runs]
            scores = [r["parsed"].get("score") for r in runs]
            subjects = [r["parsed"].get("subject_present") for r in runs]
            verdicts = [isinstance(s, int) and s >= threshold for s in scores]
            if all(v is case.should_pass for v in verdicts) and all(
                s is case.subject_present for s in subjects
            ):
                correct += 1
            if len(set(verdicts)) > 1:
                unstable += 1
        average = sum(seconds) / len(seconds) if seconds else 0.0
        rows.append((correct, -average, model, unstable, errors, average))

    for correct, _, model, unstable, errors, average in sorted(rows, reverse=True):
        print(f"{model:<34}{f'{correct}/{len(CASES)}':>7}{unstable:>7}{errors:>7}{average:>9.1f}")

    print(
        "\n正答=合否と被写体が模範解答どおり / ブレ=2回で合否が割れた / エラー=呼び出し失敗かJSON破損"
    )


if __name__ == "__main__":
    asyncio.run(main())
