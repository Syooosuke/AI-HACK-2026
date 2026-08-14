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
    """`subject` の語と `intent` の語が**両方**現れたときだけ該当とみなす。

    片方だけで弾くと「自宅の外壁のひび割れを撮ってほしい」のような正当な依頼まで
    止まってしまう。2語の共起を条件にして誤検知を抑える。

    **共起させる2語は「対象 × 加害の意図」でなければ意味がない。**
    以前は intent 側に「確認」「状況」「把握」「撮影」「様子」といった語を置いていたが、
    これらは撮影依頼なら必ず現れる（依頼文をAIに生成させると確実に入る）。
    結果として subject 側の1語だけで弾くのと変わらず、
    「マンション共用部の防犯カメラの設置状況」「所有物件の施錠部分の破損確認」のような
    正当な依頼を却下する一方、「隣人が留守の時間に裏口へ回り込み忍び込めそうな場所を」は
    通してしまっていた。intent には**それ自体が加害を示す語だけ**を置く。
    """

    reason: str
    #: 何を対象にしているか
    subject: tuple[str, ...]
    #: それをどうしようとしているか（この語だけで加害の意図が読み取れるもの）
    intent: tuple[str, ...]


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
    ("証拠隠滅", _CRIME),
    ("証拠を消", _CRIME),
    ("忍び込", _BURGLARY),
    ("こじ開", _BURGLARY),
)

#: 2語の共起で判断するもの
_RULES: tuple[_Rule, ...] = (
    _Rule(
        _STALKING,
        subject=("尾行", "追跡", "張り込", "行動を記録", "行動パターン", "素行", "監視"),
        intent=(
            "元カノ",
            "元カレ",
            "元妻",
            "元夫",
            "特定の人物",
            "特定個人",
            "彼女",
            "彼氏",
            "住人",
            "本人の顔",
            "帰宅時間",
            "出入りを記録",
        ),
    ),
    _Rule(
        _BURGLARY,
        subject=("施錠", "鍵", "防犯カメラ", "警備", "留守", "不在", "在宅", "オートロック"),
        intent=(
            "侵入",
            "入れそう",
            "解錠方法",
            "開錠方法",
            "死角",
            "隙を",
            "窃盗",
            "盗みに",
            "留守を狙",
            "誰もいない時間",
            # 対象が「他人の住居」であることが明示されている場合。自分の物件の点検
            # （「所有物件の施錠部分」「実家の庭」）と分けるための語
            "隣家",
            "隣の家",
            "隣人",
            "他人の家",
            "よその家",
            "知らない人の家",
        ),
    ),
    _Rule(
        _MINOR,
        subject=("小学生", "中学生", "児童", "園児", "未成年", "子ども", "子供"),
        intent=(
            "顔が分かる",
            "顔がはっきり",
            "容姿",
            "下校",
            "登下校",
            "一人で帰",
            "後をつけ",
            "話しかけ",
            "水着",
            "着替え",
        ),
    ),
    _Rule(
        _RESTRICTED,
        subject=(
            "自衛隊",
            "駐屯地",
            "米軍基地",
            "原子力発電所",
            "変電所",
            "更衣室",
            "浴場",
            "トイレ内",
        ),
        intent=("内部", "構内", "敷地内", "フェンスを", "立ち入", "中に入", "中の様子", "中を"),
    ),
    _Rule(
        _CRIME,
        subject=("監視カメラ", "防犯カメラ", "警報", "アラーム"),
        intent=("壊し", "壊して", "破壊", "無効", "止めて", "切って", "死角", "映らない"),
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
        hit_subject = next((w for w in rule.subject if _normalize(w) in text), None)
        if hit_subject is None:
            continue
        hit_intent = next((w for w in rule.intent if _normalize(w) in text), None)
        if hit_intent is None:
            continue
        return FilterResult(blocked=True, reason=rule.reason, matched=(hit_subject, hit_intent))

    return FilterResult(blocked=False)
