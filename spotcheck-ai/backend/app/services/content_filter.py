"""依頼テキストの安全審査（AIに依存しない部分）。

**AIの判定だけに頼らない理由**

1. スタブモード（`ORCA_STUB_MODE=true`）では LLM を呼ばないため、AI側の審査が
   丸ごと素通りする。デモ環境ではこちらが唯一の防波堤になる。
2. 実運用でも LLM は指示を無視することがある。犯罪目的の依頼を通してしまうと
   取り返しがつかないため、決定論的な検査を前段に置く（多層防御）。

ここで拾うのは**明らかに黒いもの**だけにする。判断に迷うものはAIへ渡し、
このモジュールでは通す。誤検知で正当な依頼を止める方が、サービスとしては痛いため。
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

#: 却下カテゴリ。値はクライアントに見せる却下理由の説明。
_STALKING = "特定個人の私生活を監視・追跡する目的と判断しました。"
_BURGLARY = "住居への侵入の下見と解釈できる内容が含まれています。"
_VOYEURISM = "盗撮・のぞき見を目的とする内容が含まれています。"
_MINOR = "未成年者を被写体とする依頼はお受けできません。"
_RESTRICTED = "撮影が禁止・制限されている場所が対象になっています。"
_CRIME = "違法行為を助ける内容が含まれています。"


@dataclass(frozen=True)
class _Rule:
    """`required` の語と `context` の語が**両方**現れたときだけ該当とみなす。

    片方だけで弾くと「自宅の外壁のひび割れを撮ってほしい」のような正当な依頼まで
    止まってしまう。2語の共起を条件にして誤検知を抑える。
    """

    reason: str
    required: tuple[str, ...]
    context: tuple[str, ...]


#: 単語1つで即座に却下してよいもの（言い逃れの余地がないもの）
_HARD_WORDS: tuple[tuple[str, str], ...] = (
    ("盗撮", _VOYEURISM),
    ("のぞき見", _VOYEURISM),
    ("覗き見", _VOYEURISM),
    ("ストーカー", _STALKING),
    ("つきまとい", _STALKING),
    ("待ち伏せ", _STALKING),
    ("児童ポルノ", _MINOR),
    ("下着", _VOYEURISM),
    ("空き巣", _BURGLARY),
    ("侵入経路", _BURGLARY),
)

#: 2語の共起で判断するもの
_RULES: tuple[_Rule, ...] = (
    _Rule(
        _STALKING,
        required=("尾行", "追跡", "行動を記録", "行動パターン", "監視"),
        context=("元カノ", "元カレ", "元妻", "元夫", "個人", "特定の人物", "彼女", "彼氏", "住人"),
    ),
    _Rule(
        _BURGLARY,
        required=("施錠", "鍵", "防犯カメラ", "留守", "不在", "在宅"),
        context=("確認", "調べ", "把握", "有無", "状況"),
    ),
    _Rule(
        _MINOR,
        required=("小学生", "中学生", "児童", "園児", "未成年"),
        context=("撮影", "写真", "撮って", "様子"),
    ),
    _Rule(
        _RESTRICTED,
        required=("自衛隊", "米軍基地", "原子力発電所", "変電所", "更衣室", "浴場", "トイレ内"),
        context=("撮影", "写真", "内部", "中を", "様子"),
    ),
    _Rule(
        _CRIME,
        required=("証拠", "監視カメラ"),
        context=("消し", "隠", "壊", "無効", "避け", "死角"),
    ),
)


@dataclass(frozen=True)
class FilterResult:
    """`blocked` が True なら依頼を却下する。"""

    blocked: bool
    reason: str | None = None
    #: 判定の根拠になった語。ログと監査のために残す（クライアントには見せない）
    matched: tuple[str, ...] = ()


def _normalize(text: str) -> str:
    """全角・半角、大文字・小文字、空白の違いを吸収する。

    「盗 撮」のように空白を挟んで検査をすり抜けるのを防ぐため、空白は落とす。
    """
    folded = unicodedata.normalize("NFKC", text).lower()
    return re.sub(r"\s+", "", folded)


def screen(title: str, description: str) -> FilterResult:
    """依頼のタイトルと詳細メッセージを検査する。"""
    text = _normalize(f"{title}\n{description}")

    for word, reason in _HARD_WORDS:
        if _normalize(word) in text:
            return FilterResult(blocked=True, reason=reason, matched=(word,))

    for rule in _RULES:
        hit_required = next((w for w in rule.required if _normalize(w) in text), None)
        if hit_required is None:
            continue
        hit_context = next((w for w in rule.context if _normalize(w) in text), None)
        if hit_context is None:
            continue
        return FilterResult(blocked=True, reason=rule.reason, matched=(hit_required, hit_context))

    return FilterResult(blocked=False)
