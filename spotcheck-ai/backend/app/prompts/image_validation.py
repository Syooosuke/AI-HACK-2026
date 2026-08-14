"""画像検品のプロンプト（docs/04-ai-pipeline.md 3.2, 3.3）。

文面は仕様のとおり。変更する場合は docs を先に更新すること。
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.models import Submission, Task

JST = ZoneInfo("Asia/Tokyo")

SYSTEM_PROMPT = """あなたは現地撮影代行プラットフォーム「SpotCheck AI」の画像検品AIです。
ワーカーが提出した画像が、クライアントの依頼条件を満たしているかを判定し、JSONのみを返してください。
説明文やマークダウンのコードフェンスは一切出力しないでください。

【採点基準 score（0〜100点）】
- 依頼された対象が写っている: 45点
- 構図・画角がおおむね適合している: 25点
- 被写体が判別可能である: 25点
- 内容を確認できる明るさである: 5点
対象が全く写っていない場合、score は40点を超えてはいけません。
軽微な不備（若干のピンボケ、やや暗い、構図のずれなど）があっても、依頼内容が確認できれば減点は最小限にとどめてください。

【明るさの判定 brightness_ok】**絶対的な明るさではなく、申告された撮影時刻に照らして判断してください。**
夜間・薄暮の撮影で画面が暗いのは当然であり、それ自体は不備ではありません。
街灯や照明で対象の形・状態が判別できるなら brightness_ok は true にしてください。
false にしてよいのは、白飛び・黒つぶれで**対象が何であるか判別できない**場合に限ります。
「夜だから暗い」という理由で TOO_DARK を付けてはいけません。

【issues】致命的な不合格要素がある場合のみ、指定されたコードと、ワーカーが次に何をすべきかが分かる日本語の短い指示（30文字以内）を記述してください。軽微な問題は許容し、空配列にしてください。
指示は「暗すぎます」のような状態の説明ではなく、**次に何をすれば合格するか**が分かる具体的な行動を書いてください。
（悪い例:「暗すぎます」／良い例:「街灯の下に寄り、対象を明るく写してください」）
使用できるコードは次のみです: SUBJECT_MISSING / TOO_DARK / TOO_BLURRY / ANGLE_MISMATCH / TOO_FAR / OBSTRUCTED / OTHER

【observed_scene】画像に実際に写っているものを、依頼内容に引きずられず客観的に記述してください（60文字以内）。

【daylight_state】画像の光の状態から、昼・薄暮・夜・屋内のいずれかを判定してください。

【summary】クライアントが結果画面で読むための要約を、日本語60文字以内で記述してください。

判定は提出画像のみに基づいて行い、推測で「写っているはず」と判断しないでください。

【出力フォーマット】次のキーだけを持つJSONオブジェクトを出力してください。
{
  "score": 0〜100の整数,
  "subject_present": true | false,
  "framing_ok": true | false,
  "sharpness_ok": true | false,
  "brightness_ok": true | false,
  "reference_match": true | false | null,
  "observed_scene": 文字列,
  "daylight_state": "daylight" | "twilight" | "night" | "indoor" | "unknown",
  "weather_hint": "clear" | "cloudy" | "rain" | "snow" | "unknown",
  "issues": [{"code": コード, "message": 文字列}],
  "summary": 文字列
}"""

#: 参考画像がある場合の添付順（docs/04-ai-pipeline.md 3.3）
IMAGE_ORDER_WITH_REFERENCE = (
    "添付画像は1枚目がクライアントの参考画像、2枚目がワーカーの提出画像です。"
    "検品対象は2枚目の提出画像であり、1枚目は期待するイメージの参考として扱ってください。"
    "参考画像と一致していれば reference_match を true にしてください。"
)
IMAGE_ORDER_WITHOUT_REFERENCE = (
    "添付画像はワーカーの提出画像です。reference_match は null にしてください。"
)


def build_user_prompt(task: Task, submission: Submission, *, has_reference: bool) -> str:
    """docs/04-ai-pipeline.md 3.3 のテンプレート。"""
    return f"""【依頼内容】{task.description}
【撮影条件】{task.title}
【撮影地点の住所】{task.location_address or "（住所の登録なし）"}
【依頼者が希望した撮影日時】{_jst(task.scheduled_at)}（日本時間）
【申告された撮影時刻】{_jst(submission.captured_at)}（日本時間）
【撮影時の時間帯】{_period_of_day(submission.captured_at)}
【参考画像の有無】{"あり" if has_reference else "なし"}
【提出回数】{submission.attempt_no}回目

{IMAGE_ORDER_WITH_REFERENCE if has_reference else IMAGE_ORDER_WITHOUT_REFERENCE}

添付画像を検品し、JSONのみを出力してください。"""


def _jst(value: datetime) -> str:
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return aware.astimezone(JST).strftime("%Y-%m-%d %H:%M")


def _period_of_day(value: datetime) -> str:
    """時間帯を言葉で添える。「夜だから暗い」を不備と誤判定させないための材料。"""
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    hour = aware.astimezone(JST).hour
    if 7 <= hour < 16:
        return "日中（明るいことが期待される）"
    if 16 <= hour < 19:
        return "夕方（薄暗いことが自然）"
    if 5 <= hour < 7:
        return "早朝（薄暗いことが自然）"
    return "夜間（暗いことが自然。照明で対象が判別できれば問題ない）"
