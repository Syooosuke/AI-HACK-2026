# 04. AIパイプライン仕様

本プロダクトの中核。以下の4機能を実装する。

| # | 機能 | 実行タイミング | 使用モデル |
|---|---|---|---|
| A | 依頼コンテキスト審査 | 依頼作成時（同期） | 軽量LLM |
| B | VLMによる画像検品 | 画像提出後（非同期） | VLM |
| C | 位置偽装対策 | 画像提出後（非同期） | 計算＋VLM |
| D | プライバシー自動保護 | 検品合格後（非同期） | ローカルYOLO |

---

## 1. OrcaClient（AI呼び出しの唯一の窓口）

### 1.1 OrcaRouter API仕様（確定）

**OpenAI Chat Completions 互換API。** OpenAI SDK は使わず `httpx` で直接呼ぶ。

| 項目 | 値 |
|---|---|
| ベースURL | `https://api.orcarouter.ai/v1` |
| エンドポイント | `POST /chat/completions` |
| 認証 | `Authorization: Bearer {ORCA_API_KEY}` |
| Content-Type | `application/json` |
| model | `orcarouter/{ルーター名}`（例: `orcarouter/auto`） |

`model` にはモデル名ではなく**ルーター名**を指定する。ルーターが戦略に従ってアップストリームのモデルを自動選択する（`orcarouter/auto` の既定モデルは `grok/grok-4.5`）。
**したがってコード内にモデル名を直書きしてはならない。** ルーター名は環境変数から供給する。

**リクエスト例**

```bash
curl https://api.orcarouter.ai/v1/chat/completions \
  -H "Authorization: Bearer sk-..." \
  -H "Content-Type: application/json" \
  -d '{"model":"orcarouter/auto","messages":[{"role":"user","content":"Hello"}]}'
```

**テキストのみのリクエストボディ**

```json
{
  "model": "orcarouter/auto",
  "messages": [
    { "role": "system", "content": "<システムプロンプト>" },
    { "role": "user",   "content": "<ユーザープロンプト>" }
  ],
  "temperature": 0.2,
  "max_tokens": 1500
}
```

- `temperature` は審査・検品ともに **0.2** とする（判定のブレを抑えるため）。
- `max_tokens` は **4000**。マスキング座標の問い合わせのみ 800。

> **実装時に 1500 → 4000 へ変更した。** `orcarouter/auto` は推論モデル（例: qwen3 系）へ
> ルーティングすることがあり、reasoning tokens が `max_tokens` を食い潰して
> `finish_reason="length"` かつ **本文が空** になる事象を実際に確認したため。
> あわせて、`finish_reason="length"` を検出したら上限を倍にして再試行する
> （上限 8000）実装を入れている。

**画像を含むリクエスト（OpenAI Vision形式）**

```json
{
  "model": "orcarouter/auto",
  "messages": [
    { "role": "system", "content": "..." },
    { "role": "user", "content": [
        { "type": "text", "text": "..." },
        { "type": "image_url", "image_url": { "url": "data:image/jpeg;base64,{BASE64}" } }
      ]
    }
  ]
}
```

- 画像は **base64 データURI** で送る。Storageの署名URLは有効期限があり、アップストリーム側から到達できない可能性があるため使わない。
- 送信前に**長辺1568pxへリサイズし、JPEG品質85で再エンコード**する（トークン量とレイテンシの削減）。リサイズ後の座標系で bbox が返る点に注意し、正規化座標（0〜1）で扱うことで解像度非依存にする。
- 複数画像を送る場合、`content` 配列に `image_url` を並べ、直前の `text` ブロックで「1枚目は参考画像、2枚目は提出画像」と明示する。

**レスポンス**

```json
{
  "id": "...",
  "model": "grok/grok-4.5",
  "choices": [
    { "index": 0, "message": { "role": "assistant", "content": "<本文>" }, "finish_reason": "stop" }
  ],
  "usage": { "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0 }
}
```

- 本文は `choices[0].message.content` から取得する。
- `OrcaResult.model` には**レスポンスの `model` フィールド**（実際に使われたアップストリームモデル名）を入れる。リクエストで送ったルーター名ではない。
- `usage` は `ai_invocations.response_payload` に含めて記録する。

**JSON出力の扱い**

`response_format: {"type": "json_object"}` はアップストリームのモデルによって対応状況が異なる。以下の順で対処する。

1. まず `response_format` を**付けずに**送り、プロンプトで「JSONのみを出力」と厳命する。
2. レスポンスからコードフェンス（```json ... ```）と前後の空白を除去する。
3. 先頭の `{` から対応する末尾の `}` までを抽出してパースする（前置きの文章が付いた場合の救済）。
4. それでも失敗したら、`messages` に「直前の出力はJSONとして解析できませんでした。説明を含めず、JSONオブジェクトのみを出力してください。」を追加して再試行する。

**ルーター構成（確定）**

`ORCA_ROUTER_LIGHT` / `ORCA_ROUTER_VISION` のどちらにも `orcarouter/auto` を設定し、**1つのルーターで運用する。**

ただし `orcarouter/auto` は全モデルを許可しているため、画像付きリクエストで Vision 非対応のモデルへルーティングされる可能性がある。**画像付き呼び出しで 400 系エラーやモデル非対応のエラーが返った場合は、リトライで解決しないため作業を止めて人間に報告すること**（Vision対応モデルのみを許可した専用ルーターを作成して `ORCA_ROUTER_VISION` に設定する対処が必要になる）。この場合もコード変更は不要で、環境変数の差し替えのみで解決できる設計にしておくこと。

**エラー時のHTTPステータス**

| ステータス | 対処 |
|---|---|
| 401 / 403 | リトライせず即座に `AIServiceError`。APIキー設定ミスの可能性をログに明記 |
| 429 | 指数バックオフでリトライ（`Retry-After` ヘッダがあれば優先） |
| 5xx / タイムアウト | 指数バックオフでリトライ |
| 400 | リトライせず `AIServiceError`。リクエストボディをログに残す（画像は除く） |

### 1.2 インターフェース定義

`backend/app/services/orca_client.py`

```python
class OrcaClient:
    async def complete_json(
        self,
        *,
        purpose: str,               # 'task_review' | 'image_validation' | 'environment_check' | 'result_summary'
        system_prompt: str,
        user_prompt: str,
        images: list[ImageInput] | None = None,
        response_schema: type[BaseModel],   # 期待するPydanticモデル
        tier: Literal["light", "vision"] = "light",
    ) -> OrcaResult: ...
```

```python
@dataclass
class ImageInput:
    url: str | None          # Storage署名URL
    base64_data: str | None  # OrcaRouterがURL非対応の場合に使用
    media_type: str          # "image/jpeg" 等

@dataclass
class OrcaResult:
    parsed: BaseModel        # response_schema でバリデート済み
    raw: dict                # 生レスポンス
    model: str               # 実際に使われたモデル名
    latency_ms: int
    is_stub: bool
```

### 1.3 実装要件

- `tier="light"` は `ORCA_ROUTER_LIGHT`、`tier="vision"` は `ORCA_ROUTER_VISION` の値を `model` に設定する。どちらも既定値は `orcarouter/auto`。
- **リトライ**: 429・5xx・タイムアウト・JSONパース失敗時に `ORCA_MAX_RETRIES` 回まで指数バックオフ（1s, 2s）で再試行する。401/403/400 はリトライしない。
- **JSON強制**: 上記1.1「JSON出力の扱い」の4段階に従う。
- パース結果は必ず `response_schema` で Pydantic バリデートする。失敗したらリトライ扱いとし、最終的に失敗したら `AIServiceError` を送出する。
- `httpx.AsyncClient` はアプリのライフサイクルで使い回す（リクエストごとに生成しない）。タイムアウトは `ORCA_TIMEOUT_SECONDS`。
- 全呼び出しについて `ai_invocations` にログを記録する。**画像のbase64は保存せず、URLまたは `"<image omitted>"` に置換する。**
- 呼び出しが最終的に失敗したら `AIServiceError` を送出する。

### 1.4 スタブモード（必須）

`ORCA_STUB_MODE=true` または `ORCA_API_KEY` 未設定のとき、HTTP通信を行わず固定レスポンスを返す。

| purpose | スタブ応答 |
|---|---|
| `task_review` | `decision="approved"`, `score=85`, 全checksがpass |
| `image_validation` | `attempt_no` が奇数なら `score=45`（再撮影指示 `TOO_DARK`）、偶数なら `score=88`（合格） |
| `environment_check` | 矛盾なし |
| `result_summary` | 「工事は予定通り進行中。安全対策は適切に実施されています。」 |

> `image_validation` を交互に失敗させるのは、**デモで再撮影ループを見せるため**である。この挙動は変更しないこと。

---

## 2. 機能A: 依頼コンテキスト審査

画面②「AIリクエスト審査（OrcaAI）」に対応。`app/services/task_review.py`

### 2.1 入力

- 依頼タイトル・詳細メッセージ・報酬・撮影人数
- 位置情報（緯度経度・逆ジオコーディング済み住所があれば含める）
- 撮影日時
- 参考画像（あれば最大3枚。`tier="vision"` に切り替える）

### 2.2 出力スキーマ

```python
class TaskReviewResult(BaseModel):
    decision: Literal["approved", "needs_info", "rejected"]
    score: int                      # 0-100 情報の十分性
    safety: Literal["pass", "fail"]
    validity: Literal["pass", "fail"]
    risk: Literal["pass", "fail"]
    duplication: Literal["pass", "fail"]
    rejection_reason: str | None    # rejected のときのみ。日本語
    missing_info: list[str]         # needs_info のときのみ。日本語の箇条書き
    summary: str                    # 依頼内容の要約（画面③に表示）
```

### 2.3 判定ロジック（サービス層で確定させる）

LLMの `decision` をそのまま信用せず、以下でサーバー側が最終決定する。

```
safety == "fail" or risk == "fail"        → rejected
validity == "fail"                        → needs_info
score < TASK_REVIEW_SCORE_THRESHOLD (70)  → needs_info
それ以外                                   → approved
```

`duplication` は現段階では表示のみに使い、判定には用いない（画面②の「重複・類似チェック」表示用）。

### 2.4 システムプロンプト

```
あなたは現地撮影代行プラットフォーム「SpotCheck AI」の依頼審査AIです。
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

【重複・類似チェック duplication】同一の被写体・地点に対する重複依頼と判断できる場合のみ "fail"、判断できなければ "pass" としてください。この項目は画面②の表示にのみ使われます。

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
}
```

> `duplication` と【出力フォーマット】は 2.2 の `TaskReviewResult` を満たすために必要なため、
> 実装時に追記した。キー名はスキーマと1対1で対応させること。

### 2.5 ユーザープロンプト（テンプレート）

```
以下の撮影依頼を審査してください。

【タイトル】{title}
【詳細メッセージ】{description}
【撮影地点】緯度 {lat} / 経度 {lng}{address_part}
【撮影希望日時】{scheduled_at}
【提出期限】{deadline_at}
【報酬】{reward}円 / 撮影人数 {worker_count}人
【参考画像】{has_reference_images}

JSONのみを出力してください。
```

参考画像がある場合は画像を添付し、「参考画像に写っている被写体が依頼内容と一致しているかも確認してください」を追記する。

---

## 3. 機能B: VLMによる画像検品

画面⑦「AI画像検品・安全処理」に対応。`app/services/image_validation.py`

### 3.1 出力スキーマ

```python
class ImageValidationResult(BaseModel):
    score: int                      # 0-100
    subject_present: bool           # 依頼された対象が写っているか
    framing_ok: bool                # 構図が適切か
    sharpness_ok: bool              # ピントが合っているか
    brightness_ok: bool             # 明るさが適切か
    reference_match: bool | None    # 参考画像との一致（参考画像がない場合はnull）
    observed_scene: str             # 画像に写っているものの客観的記述（機能Cで使用）
    daylight_state: Literal["daylight", "twilight", "night", "indoor", "unknown"]
    weather_hint: Literal["clear", "cloudy", "rain", "snow", "unknown"]
    issues: list[IssueItem]         # code は定義済みコードのみ
    summary: str                    # クライアント向けの日本語要約
```

```python
class IssueItem(BaseModel):
    code: Literal["SUBJECT_MISSING","TOO_DARK","TOO_BLURRY","ANGLE_MISMATCH",
                  "TOO_FAR","OBSTRUCTED","LOCATION_MISMATCH","TIMESTAMP_MISMATCH","OTHER"]
    message: str    # 画面⑧に表示する日本語の再撮影指示
```

### 3.2 システムプロンプト

```
あなたは現地撮影代行プラットフォーム「SpotCheck AI」の画像検品AIです。
ワーカーが提出した画像が、クライアントの依頼条件を満たしているかを判定し、JSONのみを返してください。
説明文やマークダウンのコードフェンスは一切出力しないでください。

【採点基準 score（0〜100点）】
- 依頼された対象が明確に写っている: 40点
- 構図・画角が依頼条件に適合している: 20点
- ピントが合っている（被写体が判別可能）: 20点
- 明るさ・露出が適切で内容を確認できる: 20点
対象が全く写っていない場合、score は30点を超えてはいけません。

【issues】不合格要素がある場合、指定されたコードと、ワーカーが次に何をすべきかが分かる日本語の短い指示（30文字以内）を記述してください。合格なら空配列にしてください。

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
}
```

> 【出力フォーマット】と、issues で使えるコードを視覚的な判定のみに限定する指示は
> 3.1 の `ImageValidationResult` を満たすために実装時に追記した。
> `LOCATION_MISMATCH` / `TIMESTAMP_MISMATCH` は 3.4 のとおりサービス層が付与するため、
> VLMには出させない。

### 3.3 ユーザープロンプト

```
【依頼内容】{task_description}
【撮影条件】{task_title}
【撮影地点の住所】{location_address}
【申告された撮影時刻】{captured_at}（日本時間）
【参考画像の有無】{has_reference}
【提出回数】{attempt_no}回目

添付画像を検品し、JSONのみを出力してください。
```

参考画像がある場合、**1枚目を参考画像、2枚目を提出画像として送り**、プロンプトでその順序を明示する。

### 3.4 合否判定（サービス層）

```
score >= SUBMISSION_SCORE_THRESHOLD (70)
  かつ subject_present == true
  かつ location_check.within_tolerance == true
  かつ location_check.timestamp_consistent == true
→ approved
それ以外 → rejected
```

`subject_present == false` の場合は、スコアに関わらず不合格とする。
位置・時刻の不整合で不合格になった場合は、`issues` に `LOCATION_MISMATCH` / `TIMESTAMP_MISMATCH` をサービス層で追加する。

---

## 4. 機能C: 位置偽装（Spoofing）対策

`app/services/location_check.py`。**LLM任せにせず、まず決定論的な計算を行う。**

### 4.1 チェック項目

| # | チェック | 方法 | 不合格条件 |
|---|---|---|---|
| C-1 | 距離検証 | 依頼地点と `captured_lat/lng` の Haversine距離 | `> LOCATION_TOLERANCE_METERS`(100m) |
| C-2 | 時刻整合 | `captured_at` と `received_at` の差 | `> TIMESTAMP_TOLERANCE_SECONDS`(300s) |
| C-3 | 撮影時間帯 | `scheduled_at` と `captured_at` の日付・時間帯 | 依頼日時から±6時間を超える（警告のみ） |
| C-4 | EXIF照合 | EXIFにGPSがある場合、申告座標との距離 | `> 200m` なら矛盾フラグ |
| C-5 | 環境整合 | VLMの `daylight_state` と `captured_at` の日出没時刻を比較 | 昼申告なのに夜画像、等 |
| C-6 | 精度チェック | `captured_accuracy_m` | `> 500m` なら警告 |

- C-5 の日出没判定は外部API不要。`astral` ライブラリ、または「6時〜18時を daylight」という簡易判定でよい（簡易判定を採用した場合はコメントで明示する）。
- EXIFにGPSが**無いこと自体は不合格にしない**（ブラウザ撮影ではEXIFにGPSが入らないため）。C-4は「あれば照合する」補助チェックである（D-02）。

### 4.2 Reality Score（信頼度スコア）

画面⑨⑩に表示する `reality_score` を以下で算出する。

```
基礎点 100
  C-1 不合格            −40
  C-2 不合格            −25
  C-4 矛盾あり          −20
  C-5 矛盾あり          −20
  C-3 警告              −5
  C-6 警告              −5
  ワーカーの trust_score が50未満  −10
下限0、上限100でクリップ
```

`within_tolerance`（C-1）と `timestamp_consistent`（C-2）は合否判定に直結する。それ以外は減点のみとする。

---

## 5. 機能D: プライバシー自動保護（D-09）

`app/services/masking.py`。**検品合格後にのみ実行**する（不合格画像は納品されないため処理不要）。

### 5.1 実装

- Ultralytics YOLO をローカル推論で使用する。
- 2モデル構成:
  - `YOLO_MODEL_PATH`（yolov8n.pt）: `person`, `car`, `truck`, `bus`, `motorcycle` クラスを検出
  - `YOLO_FACE_MODEL_PATH`（yolov8n-face.pt）: 顔を直接検出
- 重みは `models_weights/` に配置し、起動時に存在チェックする。無い場合は**警告ログを出してマスキングをスキップし、`masking_result.skipped = true` を記録する**（デモを止めないため）。

### 5.2 マスキング対象と処理

| 対象 | 検出方法 | 処理 |
|---|---|---|
| 通行人の顔 | face モデル | ガウシアンぼかし。矩形を上下左右に10%拡張 |
| 人物全体 | person クラス | **ぼかさない**（工事状況の確認に必要なため）。顔のみ処理する |
| 車両のナンバープレート | car/truck/bus の bbox 下部30%領域を候補とし、VLMに座標を問い合わせて絞り込む | 黒塗り（完全マスク） |
| 表札・住居の番地 | VLMに座標を問い合わせる | ガウシアンぼかし |

- ナンバープレートと表札は既存の軽量モデルでは精度が出ないため、**VLMに正規化座標（0〜1）で bbox を返させる**。

```python
class PrivacyRegion(BaseModel):
    kind: Literal["license_plate", "nameplate", "address_sign", "personal_document"]
    x1: float; y1: float; x2: float; y2: float   # 0.0〜1.0 の正規化座標
    confidence: float
```

- VLM呼び出しに失敗した場合も処理を止めず、YOLOで検出できた顔のみ処理する。
- ぼかし強度: 対象矩形の短辺 × `BLUR_KERNEL_RATIO`(0.15) をカーネルサイズとし、奇数に丸める。最小15px。

### 5.3 保存

- 加工後画像を `STORAGE_BUCKET_PROCESSED` に保存し、`processed_image_url` に記録する。
- **原本は削除せず `STORAGE_BUCKET_RAW` に残すが、APIレスポンスには一切含めない**（争議時の証跡として保持する）。
- `masking_result` に処理内容を記録する。

```json
{
  "skipped": false,
  "regions": [
    { "kind": "face", "method": "yolo_face", "bbox": [0.31,0.22,0.36,0.30], "blurred": true },
    { "kind": "license_plate", "method": "vlm", "bbox": [0.55,0.61,0.64,0.65], "blurred": true }
  ],
  "face_count": 3,
  "plate_count": 1,
  "processing_ms": 820
}
```

---

## 6. パイプライン統括

`app/services/submission_pipeline.py`。`POST /api/submissions` の BackgroundTasks から呼ばれる。

```
1. submissions.ai_validation_status = 'processing'
2. 機能C（決定論的チェック C-1〜C-4, C-6）を実行
3. 機能B（VLM検品）を実行         ← 失敗時は status='error' で終了
4. 機能C の C-5（環境整合）を B の出力を用いて判定
5. reality_score を算出
6. 合否判定（3.4節）
   ├─ approved:
   │    6-1. 機能D（マスキング）を実行
   │    6-2. submissions を approved で更新
   │    6-3. assignment を approved、completed_at を設定
   │    6-4. tasks.approved_worker_count += 1
   │         required_worker_count に到達したら tasks.status='completed'
   │    6-5. ワーカーの trust_score +2.0、completed_task_count += 1
   │    6-6. payments に charge / payout を作成し stub_succeeded にする（D-03）
   │    6-7. 安全処理済み画像を OrcaRouter へ送り tasks.result_summary を生成
   └─ rejected:
        6-1. submissions を rejected で更新
        6-2. assignment.retake_count < MAX_RETAKE_COUNT なら
               retake_count += 1、assignment.status='accepted'（再撮影を許可）
             そうでなければ
               assignment.status='failed'、completed_at を設定、trust_score −5.0
               → 枠が自動的に再開放される（D-08）
7. 例外発生時は ai_validation_status='error' とし、assignment を 'accepted' に戻す
   （retake_count は増やさない）
```

**すべてのDB更新は単一トランザクションで行い、失敗時はロールバックすること。**
Storage への書き込みはトランザクション外のため、失敗時は孤児ファイルが残る。許容する（削除処理は実装しない）。
