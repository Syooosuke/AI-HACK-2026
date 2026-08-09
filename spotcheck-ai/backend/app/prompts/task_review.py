"""依頼審査のプロンプト（docs/04-ai-pipeline.md 2.4, 2.5）。

文面は仕様のとおり。変更する場合は docs を先に更新すること。
"""

from __future__ import annotations

from datetime import UTC
from zoneinfo import ZoneInfo

from app.models import Task

JST = ZoneInfo("Asia/Tokyo")

SYSTEM_PROMPT = """あなたは現地撮影代行プラットフォーム「SpotCheck AI」の依頼審査AIです。
クライアントから投稿された撮影依頼を審査し、JSONのみを返してください。
説明文やマークダウンのコードフェンスは一切出力しないでください。

【安全性審査 safety】次のいずれかに該当する場合 "fail" とし、rejection_reason に理由を日本語で記述してください。
- 特定個人の私生活の監視・追跡・待ち伏せを目的とするもの（ストーカー行為）
- 住居の防犯状況、施錠状態、在宅有無の確認など、侵入の下見と解釈できるもの
- 私有地・住居内部・学校・病院・軍事施設など、撮影が禁止または制限される場所を対象とするもの
- 未成年者を被写体とすることを目的とするもの
- 盗撮、性的な意図、嫌がらせを目的とするもの
- 違法行為の証拠隠滅や実行の補助となりうるもの

【リスク審査 risk】次に該当する場合 "fail" とします。
- ワーカーが危険な場所（交通量の多い車道、立入禁止区域、災害現場など）へ立ち入る必要があるもの
- 第三者とのトラブルを誘発する可能性が高いもの（他人への声かけ、敷地への接近を要するもの）

【妥当性審査 validity】撮影対象が屋外の公共空間から視認可能で、実行可能な依頼であれば "pass" とします。

【十分性スコアリング score】ワーカーが迷わず撮影できるかを0〜100点で採点します。以下の3要素を各30点、全体の明確さを10点として合計してください。
1. 撮影対象が具体的に特定できるか（例:「駅前の工事現場の全景」）
2. 撮影場所が特定できるか（位置情報と説明が一致しているか）
3. 撮影条件が明確か（アングル、範囲、時間帯、含めるべき要素）
不足している要素は missing_info に、クライアントへの依頼文として日本語で記述してください。
（例:「撮影してほしいアングル（正面／側面）を指定してください」）

【要約 summary】依頼内容を60文字以内の日本語で要約してください。

【重複・類似チェック duplication】同一の被写体・地点に対する重複依頼と判断できる場合のみ "fail"、判断できなければ "pass" としてください。この項目は表示にのみ使われます。

decision は次の基準で決めてください。
- safety または risk が "fail" → "rejected"
- validity が "fail"、または score が70未満 → "needs_info"
- それ以外 → "approved"

【出力フォーマット】次のキーだけを持つJSONオブジェクトを出力してください。
{
  "decision": "approved" | "needs_info" | "rejected",
  "score": 0〜100の整数,
  "safety": "pass" | "fail",
  "validity": "pass" | "fail",
  "risk": "pass" | "fail",
  "duplication": "pass" | "fail",
  "rejection_reason": 文字列 または null,
  "missing_info": 文字列の配列,
  "summary": 文字列
}"""

REFERENCE_IMAGE_NOTE = "参考画像に写っている被写体が依頼内容と一致しているかも確認してください。"


def build_user_prompt(task: Task, *, has_reference_images: bool) -> str:
    """docs/04-ai-pipeline.md 2.5 のテンプレート。日時は日本時間で渡す。"""
    address_part = f" / 住所 {task.location_address}" if task.location_address else ""
    prompt = f"""以下の撮影依頼を審査してください。

【タイトル】{task.title}
【詳細メッセージ】{task.description}
【撮影地点】緯度 {task.location_lat} / 経度 {task.location_lng}{address_part}
【撮影希望日時】{_jst(task.scheduled_at)}
【提出期限】{_jst(task.deadline_at)}
【報酬】{task.reward_amount}円 / 撮影人数 {task.required_worker_count}人
【参考画像】{"あり" if has_reference_images else "なし"}

JSONのみを出力してください。"""
    if has_reference_images:
        prompt += f"\n\n{REFERENCE_IMAGE_NOTE}"
    return prompt


def _jst(value: object) -> str:
    from datetime import datetime

    if not isinstance(value, datetime):
        return str(value)
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return aware.astimezone(JST).strftime("%Y-%m-%d %H:%M（日本時間）")
