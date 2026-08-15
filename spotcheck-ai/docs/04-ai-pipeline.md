# 04. AIパイプライン仕様

本プロダクトの中核。以下の5機能を実装している。

| # | 機能 | 実行タイミング | 使うもの | 実装 |
|---|---|---|---|---|
| A | 依頼コンテキスト審査 | 依頼作成時（**同期**） | 決定論フィルタ ＋ LLM（合議） | `content_filter.py` / `task_review.py` |
| B | VLMによる画像検品 | 画像提出後（非同期） | VLM（境界のみ再判定） | `image_validation.py` |
| C | 位置偽装対策 | 画像提出後（非同期） | 計算 ＋ Bの出力 | `location_check.py` |
| D | プライバシー自動保護 | 検品合格後（非同期） | ローカルYOLO ＋ VLM座標 | `masking.py` |
| E | 投稿サムネイルの生成 | 依頼公開後（非同期） | Street View ＋ VLM ＋ 画像生成 | `thumbnail_service.py` |

補助的な生成として、依頼文の下書き（`task_description.py`）と
クライアント向けの調査結果総括（`result_summary.py`）がある。

---

## 1. OrcaClient（AI呼び出しの唯一の窓口）

`backend/app/services/orca_client.py`。**OpenAI/Anthropic のSDKを直接 import してはならない。**

### 1.1 OrcaRouter API仕様

**OpenAI Chat Completions 互換API。** OpenAI SDK は使わず `httpx` で直接呼ぶ。

| 項目 | 値 |
|---|---|
| ベースURL | `ORCA_API_BASE_URL`（既定 `https://api.orcarouter.ai/v1`） |
| エンドポイント | `POST /chat/completions` |
| 認証 | `Authorization: Bearer {ORCA_API_KEY}` |
| Content-Type | `application/json` |
| model | ルーター名（`orcarouter/auto`）またはモデルID（`anthropic/claude-opus-5`） |

**`model` の値をコードへ直書きしてはならない。** 必ず環境変数から供給する。
送信先の決定は次の優先順位（`OrcaClient.complete_json()`）。

1. `model` 引数 — 多数決で個別のモデルを指名するときに使う
2. `model_key` に割り当てられた `ORCA_MODEL_*`
3. `tier` の既定（`ORCA_ROUTER_LIGHT` / `ORCA_ROUTER_VISION`）

**リクエストボディ**

```json
{
  "model": "anthropic/claude-opus-5",
  "messages": [
    { "role": "system", "content": "<システムプロンプト>" },
    { "role": "user",   "content": "<ユーザープロンプト>" }
  ],
  "temperature": 0.2,
  "max_tokens": 4000,
  "response_format": { "type": "json_schema", "json_schema": { … } }
}
```

| 定数 | 値 | 理由 |
|---|---|---|
| `TEMPERATURE` | 0.2 | 審査・検品ともに固定。判定のブレを抑える |
| `DEFAULT_MAX_TOKENS` | 4000 | 推論モデルへ振られると reasoning tokens が上限を食い潰し、`finish_reason="length"` で**本文が空**になる |
| `COORDINATE_MAX_TOKENS` | 800 | マスキング座標の問い合わせのみ |
| `MAX_TOKENS_CEILING` | 8000 | `finish_reason="length"` を検出したら上限を倍にして再試行する。その上限 |
| `MAX_IMAGE_LONG_EDGE` | 1568 | 送信前に長辺をこのサイズへ縮小し、JPEG品質85で再エンコードする |
| `BACKOFF_SECONDS` | (1.0, 2.0) | リトライの待ち時間 |

**画像を含むリクエスト（OpenAI Vision形式）**

```json
{
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

- 画像は **base64 データURI** で送る。Storageの署名URLは有効期限があり、アップストリーム側から
  到達できない可能性があるため使わない（`ImageInput.url` は監査ログ用の参照としてのみ保持する）。
- 送信前に `encode_image_for_vlm()` で**長辺1568pxへ縮小し、JPEG品質85で再エンコード**する。
  bbox は正規化座標（0〜1）で扱うため、縮小しても座標の解釈は変わらない。
- 複数画像を送る場合、`content` 配列に `image_url` を並べ、直前の `text` ブロックで
  「1枚目は参考画像、2枚目は提出画像」と明示する。

**レスポンス**

```json
{
  "id": "...",
  "model": "anthropic/claude-opus-5",
  "choices": [
    { "index": 0, "message": { "role": "assistant", "content": "<本文>" }, "finish_reason": "stop" }
  ],
  "usage": { "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0 }
}
```

- 本文は `choices[0].message.content` から取得する。
- `OrcaResult.model` には**レスポンスの `model` フィールド**（実際に使われたアップストリームモデル名）を入れる。
  リクエストで送った値ではない。スタブ時は `"stub"`。
- `usage` は `ai_invocations.response_payload` に含めて記録する。

**JSON出力の扱い**

**プロンプトで「JSONだけ返して」と頼むのをやめ、`response_format` でAPIに形を強制させる。**
指示を無視してJSON以外を返すモデルが実在したため。

> **Pydantic の `model_json_schema()` をそのまま渡してはならない。**
> アップストリームごとに要求が違い、実測で次の 400 が返った。
> **400 はリトライされないため、踏むとその用途が丸ごと落ちる。**
>
> | アップストリーム | 400 の理由 |
> |---|---|
> | Anthropic 系 | `object` に `additionalProperties: false` が明示されていない |
> | Gemini 系 | `$defs` / `$ref` を解釈できない（入れ子のモデルを持つスキーマで発生） |
>
> `_normalize_schema()` が `$ref` を実体へ展開し、すべての `object` に
> `additionalProperties: false` を付けて両方の制約を満たす（`strict: false` で送る）。
> **スキーマに入れ子のモデルを増やしたときは、実モデルへ1回投げて確認すること。**

解析は次の順で対処する（`extract_json_object()`）。

1. `response_format` で形を指定する。
2. コードフェンス（```json … ```）と前後の空白を除去する。
3. 先頭の `{` から対応する末尾の `}` までを抽出してパースする（前置きの文章が付いた場合の救済）。
   文字列リテラル内の括弧・エスケープを考慮した手書きの走査で行う。
4. それでも失敗したら、直前の出力を `assistant` として見せたうえで
   「直前の出力はJSONとして解析できませんでした。説明を含めず、JSONオブジェクトのみを出力してください。」
   を追加して再試行する。
5. ただし `finish_reason == "length"` のときは形式の問題ではないため、**指摘の代わりに `max_tokens` を倍にする**。

**ルーター構成**

当初は `ORCA_ROUTER_LIGHT` / `ORCA_ROUTER_VISION` のどちらにも `orcarouter/auto` を設定していたが、
**実測の結果これをやめ、tier の既定にも具体的なモデルを置いている。**

`orcarouter/auto` は呼び出しごとに振り先が変わる（同じプロンプトで `qwen3.7-plus` と
`deepseek-v4-pro` の両方を観測した）。推論モデルへ当たると reasoning tokens だけで `max_tokens` を
使い切り、`finish_reason="length"` で**本文が空**のまま返る。依頼文生成（当時 `max_tokens=300`）では
8件中7件がこれで失敗した。

| 環境変数 | 値 | 理由 |
|---|---|---|
| `ORCA_ROUTER_LIGHT` | `openai/gpt-5.4-mini` | 推論に予算を取られない。実測1.4秒で8/8成功 |
| `ORCA_ROUTER_VISION` | `qwen/qwen3-vl-235b-a22b-instruct` | Vision非対応へ振られる事故が起きない |

**エラー時のHTTPステータス**

| ステータス | 対処 |
|---|---|
| 401 / 403 | リトライせず即座に `AIServiceError`。APIキー設定ミスの可能性をログに明記 |
| 400（画像なし） | リトライせず `AIServiceError`。ボディの先頭500文字をログに残す |
| 400（**画像あり**） | Vision 非対応モデルへ振られた可能性。リトライで解決しないため、`ORCA_ROUTER_VISION` の見直しを促して止める |
| 429 | 指数バックオフでリトライ（`Retry-After` ヘッダがあれば優先） |
| 5xx / タイムアウト | 指数バックオフでリトライ |

画像付きで 400 が返る事態は環境変数の差し替えだけで解決できる設計にしてある。**コード変更は不要。**

### 1.2 モデルの振り分け（用途 × リスク）

**分類軸は「画像の有無」ではなく「間違えたときの損失」。**
画像の有無で分けると、中核の検品と飾りのサムネイルが同じ扱いになってしまう。

| 段階 | 間違えると何が起きるか | 該当するプロンプト |
|---|---|---|
| S: 取り返しがつかない | 犯罪の幇助・不当な失格・個人情報の公開 | 依頼審査 / **画像検品** / マスキング座標 |
| A: 品質に響くが回復可能 | 納品文が的外れ | 調査結果の総括 |
| B: やり直しが効く | 見た目が少し悪い | 詳細メッセージ生成 / サムネイル情景説明 |

用途ごとに環境変数でモデルを指定する。未設定なら tier の既定へ落ちる。

| 環境変数 | 用途 | `model_key` | tier |
|---|---|---|---|
| `ORCA_MODEL_TASK_REVIEW` | 依頼審査 | `task_review` | 参考画像があれば vision、無ければ light |
| `ORCA_MODEL_IMAGE_VALIDATION` | 画像検品 | `image_validation` | vision |
| `ORCA_MODEL_MASKING` | マスキング座標 | `masking` | vision |
| `ORCA_MODEL_RESULT_SUMMARY` | 調査結果の総括 | `result_summary` | vision |
| `ORCA_MODEL_TASK_DESCRIPTION` | 詳細メッセージ生成 | `task_description` | light |
| `ORCA_MODEL_THUMBNAIL` | サムネイル情景説明 | `thumbnail` | vision |

> **`orcarouter/auto` を重要な用途に使わない。**
> 中身は予告なく変わる（仕様書が「既定は grok/grok-4.5」と書いていた時期に、
> 実体は `qwen3.7-plus` だった）。品質が落ちても気づけないため、明示指定する。

実測にもとづく現在の割り当ては次のとおり。数字は `scripts/bench_task_review.py`
（正当14件＋悪意8件）と `scripts/bench_models.py`（実写真ケース）の結果。

| 用途 | モデル | 実測 |
|---|---|---|
| 依頼審査 | `anthropic/claude-opus-5` | 正当14/14・悪意8/8。まれにJSON破損があるため合議で吸収する |
| 画像検品 | `anthropic/claude-opus-5` | 5/5・ブレ0。合格側スコアの余裕が **+18** で最大（5.9秒） |
| 詳細メッセージ生成 | `openai/gpt-5.4-mini` | 8/8成功・1.4秒。`openai/gpt-5-mini` は推論に予算を使い切り **0/4** |

> **検品モデルは「正答率」だけで選ばない。**
> `claude-haiku-4.5` は5/5正答だが、合格すべき写真のスコアが 72〜75 と
> しきい値（当時70）の**わずか+2**しかない。振れ幅を考えると、まともな写真が再撮影になる。
> 合格側の余裕（min(合格スコア) − しきい値）も併せて見ること。

#### 冗長化 — 重要な判定は1回の呼び出しに賭けない

同じ画像・同じプロンプト・`temperature=0.2` でも、**スコアが 30 と 95 のように
合否をまたいで振れる**ことを実測した。決定性はパラメータでは買えないため、
呼び出しを重ねて多数決で吸収する。

| 環境変数 | 効果 |
|---|---|
| `ORCA_REVIEW_JURY` | 依頼審査を、主モデル＋ここに並べたモデルで**並行**実行し多数決 |
| `ORCA_VALIDATION_JURY` | 検品のスコアが境界に入ったときだけ追加で判定させ多数決 |
| `ORCA_VALIDATION_BOUNDARY` | 境界の幅（既定15）。`\|score − しきい値\| ≤ 幅` で再判定 |

**全件を3回呼ばないのは、振れるのが境界付近だけだから。** 明らかな合格・不合格は
2回とも一致した。待っているのは現地のワーカーなので、待ち時間を一律3倍にする価値はない。

依頼審査の票が同数のときは `rejected > needs_info > approved` の順に**慎重な側**を採る
（`task_review._TIE_BREAK_ORDER`）。公開してからでは取り返しがつかないためだが、
**この非対称性は無条件ではない。** `rejected` は行き止まりで、依頼者は書き直して再申請できない
（`task_service.resubmit_task()` は `NEEDS_INFO` の依頼しか受け付けない）。誤った却下はそのまま失注になる。

> **合議は2モデルで組まない。** 2モデルで意見が割れると必ず同数になり、
> 上の規則で常に `rejected` に倒れる。**主モデル＋合議2つの3票**にすること。

呼び出しが1件失敗しても、残った票で判定を続ける。全滅したときだけ `AIServiceError`。

#### モデルを変えるときの回帰確認

モデルもプロンプトも変わる。**「気づいたら精度が落ちていた」を防げるのは実測だけ**なので、
変更時は必ず次の2本を流す。実際に課金が発生するためCIには入れない。

```bash
cd backend
ORCA_API_KEY=... ./.venv/bin/python -m scripts.bench_models        # 画像検品
ORCA_API_KEY=... ./.venv/bin/python -m scripts.bench_task_review   # 依頼審査
```

- `bench_models` … 実写真のケースについて、合否・被写体の有無が模範解答と一致するか、
  2回流して合否が割れないか、何秒かかるかを表で出す。
  うち6ケースは**現地の粗い写真**（暗い / 真っ暗に近い / 手ブレ / 隅に寄る / 傾き / 遠い /
  夜間＋手ブレ）を加工で再現したもので、**すべて合格すべきもの**として置いてある。
  ここが落ちる状態は「ワーカーが達成できない検品」になっている合図。
- `bench_task_review` … 正当な依頼14件（**依頼文生成AIの実出力**を使う）と明らかに黒い依頼8件を、
  `content_filter` → 審査プロンプトの順に本番と同じ経路で通す。
  `--combo a,b,c` を付けると `ORCA_MODEL_TASK_REVIEW` ＋ `ORCA_REVIEW_JURY` の
  多数決そのものを評価できる。**見るべき指標は「誤却下」**（正当な依頼を却下した数）。

### 1.3 インターフェース定義

```python
class OrcaClient:
    async def complete_json(
        self,
        *,
        purpose: Purpose,                    # ai_invocations.purpose に入る
        system_prompt: str,
        user_prompt: str,
        response_schema: type[BaseModel],    # 期待するPydanticモデル
        images: list[ImageInput] | None = None,
        tier: Literal["light", "vision"] = "light",
        model_key: ModelKey | None = None,   # ORCA_MODEL_* の選択キー
        model: str | None = None,            # 多数決で個別に指名するとき
        max_tokens: int = DEFAULT_MAX_TOKENS,
        related_type: str | None = None,
        related_id: uuid.UUID | None = None,
        recorder: InvocationRecorder | None = None,
        context: dict | None = None,         # スタブ応答の分岐に使う補助情報
    ) -> OrcaResult: ...

    async def generate_image(self, *, prompt: str, size: int, ...) -> GeneratedImage: ...
    @property
    def image_generation_enabled(self) -> bool: ...
```

```python
@dataclass
class ImageInput:
    url: str | None = None            # 監査ログ用の参照
    base64_data: str | None = None    # 実際に送るデータ
    media_type: str = "image/jpeg"

@dataclass
class OrcaResult:
    parsed: BaseModel        # response_schema でバリデート済み
    raw: dict                # 生レスポンス
    model: str               # 実際に使われたモデル名（スタブ時は "stub"）
    latency_ms: int
    is_stub: bool
```

`Purpose` は `task_review` / `task_description_generation` / `image_validation` /
`environment_check` / `result_summary` / `thumbnail_generation` の6種。
`ModelKey` はこれと1対1ではない（**マスキングは `image_validation` の purpose を使いながら
別モデルを割り当てられる**ようにするため）。

### 1.4 実装要件

- **リトライ**: 429・5xx・タイムアウト・JSONパース失敗時に `ORCA_MAX_RETRIES` 回まで
  指数バックオフ（1s, 2s）で再試行する。401/403/400 はリトライしない。
- パース結果は必ず `response_schema` で Pydantic バリデートする。最終的に失敗したら `AIServiceError`。
- `httpx.AsyncClient` はアプリのライフサイクルで使い回す（リクエストごとに生成しない）。
  タイムアウトは `ORCA_TIMEOUT_SECONDS`。停止時に `lifespan` が `close()` する。
- 全呼び出しについて `ai_invocations` にログを記録する。
  **画像のbase64は保存せず、URLまたは `"<image omitted>"` に置換する。**
- 記録は `ai_invocation_repo.create_autonomous()`（独立セッション＋コミット）で行う。
  **業務トランザクションがロールバックしても監査ログは残る。** 記録に失敗しても本処理は止めない。

### 1.5 スタブモード（必須）

`ORCA_STUB_MODE=true` または `ORCA_API_KEY` 未設定のとき、HTTP通信を行わず固定レスポンスを返す。
スタブ応答も実呼び出しと同じエンベロープに包み、**解析経路を共通化する**。

| purpose | スタブ応答 |
|---|---|
| `task_review` | `decision="approved"` / `score=85` / 全checksが `pass` |
| `task_description_generation` | タイトルを差し込んだ定型文 |
| `image_validation`（検品） | `attempt_no` が**奇数なら `score=45`**（`ANGLE_MISMATCH`）、**偶数なら `score=88`**（合格） |
| `image_validation`（`stage="masking"`） | `{"regions": []}` |
| `environment_check` | 矛盾なし |
| `result_summary` | 依頼タイトルと検品所見をつないだ文 |

> **`image_validation` を交互に失敗させるのは、デモで再撮影ループを見せるためである。この挙動は変更しないこと。**

スタブが画像を見られないことによる副作用を、次の2点で潰してある。

1. **不合格の理由に「暗すぎます」を使わない。** 夜間の撮影で毎回それが出ると、
   画像を見ていないことが露骨に分かる。時間帯に依存しない `ANGLE_MISMATCH` を使う。
2. **`daylight_state` を申告された撮影時刻から決める**（`_stub_daylight_state()`）。
   固定値にすると夜間撮影で `daylight` を返し、C-5 の環境整合チェックが誤って不整合と判定する。
3. `result_summary` は依頼のタイトルと検品所見をつなぐ。固定文だとどの依頼でも同じ総括になる。

> **スタブモードでは LLM 審査が丸ごと素通りする。** 決定論フィルタ（2.2.1）が唯一の防波堤になる。

---

## 2. 機能A: 依頼コンテキスト審査

画面②「AIリクエスト審査（OrcaAI）」に対応。`app/services/task_review.py`

### 2.1 入力

- 依頼タイトル・詳細メッセージ・報酬・撮影人数
- 位置情報（緯度経度・逆ジオコーディング済み住所があれば含める）
- 撮影希望日時・提出期限（**日本時間に変換して渡す**）
- 参考画像（あれば最大3枚。あるときだけ `tier="vision"` に切り替える）

参考画像の取得に失敗したものはスキップし、審査自体は続行する。
スタブモードでは画像を送らないため、無駄なダウンロードも行わない。

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

### 2.2.1 AIより前に通す決定論フィルタ（`app/services/content_filter.py`）

**LLMを呼ぶ前に、キーワードによる安全審査を必ず通す。** 該当したらAIを呼ばずに `rejected` で確定する。

理由は2つ。

1. **スタブモード（`ORCA_STUB_MODE=true`）ではLLMを呼ばない。** デモ環境はこの設定で
   動くことがあり、AI側の審査が丸ごと素通りする。フィルタが無いと犯罪目的の依頼がそのまま公開される
2. 実運用でもLLMは指示を無視することがある。取り返しのつかない却下漏れを防ぐ多層防御

判定は2種類。

| 種類 | 例 | 考え方 |
|---|---|---|
| 単語1つで却下 | 盗撮 / のぞき見 / ストーカー / つきまとい / 待ち伏せ / 児童ポルノ / 下着 / 空き巣 / 侵入経路 / 証拠隠滅 / 忍び込 / こじ開 | 言い逃れの余地が無いもの |
| 2語の共起で却下 | 「施錠」＋「侵入」、「行動パターン」＋「元カノ」 | 片方だけでは正当な依頼を巻き込むため |

共起ルールは5系統（ストーカー / 住居侵入 / 未成年 / 撮影制限区域 / 犯罪の補助）。

**共起させる2語は「対象 × 加害の意図」でなければならない。**
当初は意図の側に「確認」「状況」「把握」「撮影」「様子」を置いていたが、
これらは撮影依頼なら必ず現れる（依頼文をAIに生成させると確実に入る）。
結果として対象側の1語だけで弾くのと同じになり、実測で次の取り違えが起きていた。

- 「マンション共用部の防犯カメラの設置状況」「所有物件の施錠部分の破損確認」→ **誤って却下**
- 「隣人が留守の時間に裏口へ回り込み、忍び込めそうな場所を」→ **素通り**

意図の側には**それ自体が加害を示す語だけ**を置く（侵入 / 死角 / 解錠方法 / 窃盗 / 下校 / 敷地内 など）。
対象が他人の住居であることが要点になる規則では、「隣家」「他人の家」のように
**対象を限定する語**を意図側に置き、自分の物件の点検と切り分ける。

**誤検知を抑える方を優先する。** 判断に迷うものはフィルタでは通し、AIの審査に委ねる。
（「自宅の外壁のひび割れを撮ってほしい」を止めてしまう方が、サービスとしては痛い）

検査前に NFKC 正規化して**空白を除く**。「盗 撮」「ｽﾄｰｶｰ」のような小細工をすり抜けさせない。

該当した場合は、AIの判定結果と同じ形（`safety="fail"` / `score=0`）に整えて保存し、
判定の根拠になった語はログにのみ残す（**クライアントには見せない**）。

### 2.3 判定ロジック（サービス層で確定させる）

LLMの `decision` をそのまま信用せず、以下でサーバー側が最終決定する（`task_review.decide()`）。

```
safety == "fail" or risk == "fail"        → rejected
validity == "fail"                        → needs_info
score < TASK_REVIEW_SCORE_THRESHOLD (70)  → needs_info
それ以外                                   → approved
```

`duplication` は表示のみに使い、判定には用いない（画面②の「重複・類似チェック」表示用）。

合議がある場合は、**各モデルの回答を個別に `decide()` にかけてから多数決**を取る
（`majority_decision()`）。表示に使う内容は、採用された判定を出した回答のうち最初のもの。
LLM の生の判定は `review_feedback.llmDecision` に残す。

### 2.4 システムプロンプト（`app/prompts/task_review.py`）

> **「〜と解釈できるもの」で fail を定義してはならない。**
> 当初のこの文面では、実測した6モデルすべてが正当な依頼の6〜8割を却下した
> （`orcarouter/auto` で 3/14、`gpt-5.4-mini` で 4/14 しか承認されない）。
> 「所有物件の玄関ドアの施錠部分の破損確認」まで「侵入の下見と解釈できる」として
> 落ちる。**モデルを変えても直らない。** fail の条件は
> 「依頼文から意図が読み取れる場合」に限定し、pass にすべき例を明示する。

```
あなたは現地撮影代行プラットフォーム「SpotCheck AI」の依頼審査AIです。
クライアントから投稿された撮影依頼を審査し、JSONのみを返してください。
説明文やマークダウンのコードフェンスは一切出力しないでください。

【前提】このサービスの主な用途は、不動産の管理・空室確認、屋外広告の掲出監査、工事の進捗確認、
設備や公共物の不具合の記録といった**正当な現況確認**です。投稿される依頼の大半はこれに当たります。
審査は**依頼文から実際に読み取れる目的**に対して行ってください。
「悪用されうる」「そう解釈されうる」という想像を根拠に "fail" としてはいけません。
却下された依頼は書き直して再申請できません。**正当な依頼を1件却下する損失は、判断に迷う依頼を1件通す損失より大きい**と考えてください。
迷ったときは "pass" とし、足りない点は score と missing_info で表現してください。

【安全性審査 safety】次のいずれかの**意図が依頼文から読み取れる場合に限り** "fail" とし、rejection_reason に理由を日本語で記述してください。
- 特定個人の私生活の監視・追跡・待ち伏せ、行動パターンの記録（ストーカー行為）
- 他人の住居への侵入の下見（不在・留守を突く、施錠を破る方法を探る、防犯設備の死角を探すなど、侵入や窃盗を示す記述があるもの）
- 住居内部・更衣室・浴場など、他人のプライベートな空間の内部を写すこと
- 学校・病院・軍事施設などの**内部や敷地内へ立ち入って**撮影すること
- 未成年者本人を被写体とすること（顔が分かる撮影、下校の追跡など）
- 盗撮、性的な意図、嫌がらせ
- 違法行為の証拠隠滅や実行の補助（防犯・監視カメラの破壊や無効化など）

次はいずれも **"pass"** です。安全性を理由に却下してはいけません。
- 自分が所有・管理・居住する物件（外壁、玄関、共用部、庭、駐車場など）の状態や破損の確認
- 防犯カメラ・オートロック・施錠部分といった**設備そのものの設置状況や故障の確認**
  （侵入・死角・解錠方法を探る記述が無い限り、管理者・居住者による点検として扱う）
- 空室・営業状況・不在（テナント募集中かどうか）の確認
- 店舗・商業施設など**公開された空間**が、外から見える範囲で写ること（住居内部とは区別してください）
- 建物やその外構が私有地にあること、隣家や第三者の建物が画面に写り込むこと
- 通行人・利用者が写り込むこと（顔は合格後に自動でマスキングされます）
- 公園・通学路・道路など公共の場所の設備や損傷の確認（未成年者本人が被写体でなければ "pass"）

【リスク審査 risk】**ワーカーの身体の安全**が脅かされる場合に限り "fail" とします。
- 立入禁止区域、災害現場の危険箇所、高速道路や線路上など、危険な場所への立ち入りを要するもの
- 高所・水域など、転落や事故の危険が具体的にあるもの
公道・共用部・店舗前など、通常人が立ち入れる場所から撮影できる依頼は "pass" とします。
近隣住民や通行人と口論になるかもしれない、不審に思われるかもしれない、といった
**想像上のトラブルを理由に "fail" としてはいけません。**

【妥当性審査 validity】明らかに実行不可能（存在しない場所、視認不可能な対象など）な場合のみ "fail" とします。
**情報が足りないだけの依頼は "pass" とし、score と missing_info で表してください。**

【十分性スコアリング score】ワーカーが迷わず撮影できるかを0〜100点で採点します。以下の3要素を各30点、全体の明確さを10点として合計してください。
1. 撮影対象が具体的に特定できるか（例:「駅前の工事現場の全景」）
2. 撮影場所が特定できるか（位置情報と説明が一致しているか）
3. 撮影条件が明確か（アングル、範囲、時間帯、含めるべき要素）
撮影地点の座標が与えられているため、**店舗名や施設名などの固有名詞が無いことを理由に大きく減点しないでください。**
現地へ行けば対象が分かる程度に書けていれば70点以上を目安とし、あれば望ましい程度の情報の不足は
減点ではなく missing_info に書いてください。
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
}
```

### 2.5 ユーザープロンプト

```
以下の撮影依頼を審査してください。

【タイトル】{title}
【詳細メッセージ】{description}
【撮影地点】緯度 {lat} / 経度 {lng}{ / 住所 {address}}
【撮影希望日時】{scheduled_at}（日本時間）
【提出期限】{deadline_at}（日本時間）
【報酬】{reward}円 / 撮影人数 {worker_count}人
【参考画像】あり | なし

JSONのみを出力してください。
```

参考画像がある場合は画像を添付し、末尾に
「参考画像に写っている被写体が依頼内容と一致しているかも確認してください。」を追記する。

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
    observed_scene: str = ""        # 画像に写っているものの客観的記述（機能Cで使用）
    daylight_state: Literal["daylight", "twilight", "night", "indoor", "unknown"] = "unknown"
    weather_hint: Literal["clear", "cloudy", "rain", "snow", "unknown"] = "unknown"
    issues: list[IssueItem]         # code は定義済みコードのみ
    summary: str = ""               # クライアント向けの日本語要約
```

```python
class IssueItem(BaseModel):
    code: Literal["SUBJECT_MISSING","TOO_DARK","TOO_BLURRY","ANGLE_MISMATCH",
                  "TOO_FAR","OBSTRUCTED","LOCATION_MISMATCH","TIMESTAMP_MISMATCH","OTHER"]
    message: str    # 画面⑧に表示する日本語の再撮影指示
```

### 3.2 システムプロンプト（`app/prompts/image_validation.py`）

> **合格の基準は「きれいに撮れているか」ではなく「依頼者が判断できるか」。**
> 当初の配点（対象40 / 構図20 / ピント20 / 明るさ20）では、**構図と写りの良さで60点**を占め、
> 対象が写っていても粗ければ落ちる。実測でも、ブレた写真が 72点（当時のしきい値70に対し **+2**）と
> 合否の境目に張り付き、`TOO_BLURRY` が付いていた。
> 現地で1枚撮るだけのワーカーには達成が難しく、再撮影の上限（2回）を超えると受注が取り消される。
>
> 配点を「対象が写っている60 / 状態が読み取れる25 / 構図10 / 明るさ5」に組み替え、
> 傾き・端寄り・軽いブレ・暗さを減点理由から外した。**対象の有無（`subject_present`）と
> 位置・時刻の検証は緩めていない**（3.4）。
>
> | | 変更前 | 変更後 |
> |---|---|---|
> | 合格すべき7ケースの最低score | 72（しきい値70 / 余裕 **+2**） | 76（しきい値60 / 余裕 **+16**） |
> | 不合格にすべき2ケース | 10 | 20（しきい値との差 −40） |
> | 粗い写真に付いた issues | `TOO_BLURRY` | なし |

```
あなたは現地撮影代行プラットフォーム「SpotCheck AI」の画像検品AIです。
ワーカーが提出した画像が、クライアントの依頼条件を満たしているかを判定し、JSONのみを返してください。
説明文やマークダウンのコードフェンスは一切出力しないでください。

【判定の基本方針】**撮影するのはスタジオの撮影者ではなく、現地に立ち寄った一般のワーカーです。**
手持ちのスマートフォンで、限られた時間に、離れた位置から撮ることになります。
判断の基準は「きれいに撮れているか」ではなく、**依頼者が知りたかったことを、この写真から判断できるか**です。
不合格にすると再撮影になり、回数の上限（2回）を超えるとワーカーの受注そのものが取り消されます。
**判断できるのに不合格にする損失は、多少粗い写真を合格にする損失よりはるかに大きい**と考えてください。
迷ったときは合格側に倒してください。

【採点基準 score（0〜100点）】
- 依頼された対象が写っている: 60点
- 対象の状態・状況が読み取れる（依頼者の知りたいことが分かる）: 25点
- 構図・画角: 10点
- 明るさ: 5点
対象が写っていて、その状態が読み取れるなら、**score は70点を下回らせないでください。**
対象が全く写っていない場合、score は40点を超えてはいけません。

次はいずれも**減点の理由になりません**（構図・明るさの10点＋5点の枠内でのみ調整してください）。
- 対象が画面の中央になく、端に寄っている／余計なものが一緒に写っている
- 写真が傾いている
- 手ブレやピントの甘さがあるが、対象が何であるかは分かる
- やや遠く、対象が小さめに写っているが、状態は読み取れる
- 夜間・逆光・曇天で全体が暗い、または一部が白飛びしている

【明るさの判定 brightness_ok】**絶対的な明るさではなく、申告された撮影時刻に照らして判断してください。**
夜間・薄暮の撮影で画面が暗いのは当然であり、それ自体は不備ではありません。
街灯や照明で対象の形・状態が判別できるなら brightness_ok は true にしてください。
false にしてよいのは、白飛び・黒つぶれで**対象が何であるか判別できない**場合に限ります。
「夜だから暗い」という理由で TOO_DARK を付けてはいけません。

【構図・鮮明さの判定 framing_ok / sharpness_ok】
対象が画面に収まっており、何が写っているか分かるなら framing_ok は true にしてください。
中央から外れている、傾いている、余白が多い、といった理由で false にしてはいけません。
sharpness_ok も同様に、**対象の形と状態が読み取れるなら true** です。
拡大すると粗い、細部が甘い、といった理由で false にしてはいけません。

【第三者・顔の扱い】
通行人・施設利用者などの顔や人物が写っていること自体は許容してください。
顔・人物などのプライバシー情報は検品合格後の専用マスキング処理で保護するため、
それらの存在だけを理由に score を下げる、subject_present / framing_ok / sharpness_ok /
brightness_ok を false にする、issues を追加する、再撮影を要求する、といった判定をしてはいけません。
行列・混雑・施設の利用状況などが依頼対象の場合、人物を含む光景が写っていることは依頼条件への適合として評価してください。
OBSTRUCTED を使用できるのは、人物などによって依頼対象そのものが判別不能なほど完全に隠れている場合だけです。

【issues】**再撮影させなければ依頼が果たせない場合のみ**記述し、それ以外は必ず空配列にしてください。
issues を付けてよいのは次の場合だけです。
- SUBJECT_MISSING … 依頼された対象が写っていない
- TOO_DARK … 黒つぶれ・白飛びで**対象が何であるか判別できない**
- TOO_BLURRY … ブレやボケが激しく**対象が何であるか判別できない**
- ANGLE_MISMATCH … 依頼で指定された面や向きと明らかに違い、知りたい状態が確認できない
- TOO_FAR … 遠すぎて**対象の状態がまったく読み取れない**
- OBSTRUCTED … 対象が完全に隠れている
- OTHER … 上のいずれでもない致命的な理由

**「もっとこう撮ればより良い」という助言を issues に書いてはいけません。**
対象が判別できるのに TOO_DARK / TOO_BLURRY / ANGLE_MISMATCH / TOO_FAR を付けることは誤りです。
合格（score が70点以上）と判定した場合、issues は必ず空配列にしてください。
記述するときは、ワーカーが次に何をすべきかが分かる日本語の短い指示（30文字以内）にしてください。
「暗すぎます」のような状態の説明ではなく、**次に何をすれば合格するか**が分かる具体的な行動を書いてください。
（悪い例:「暗すぎます」／良い例:「街灯の下に寄り、対象を明るく写してください」）

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

> `LOCATION_MISMATCH` / `TIMESTAMP_MISMATCH` は 3.4 のとおりサービス層が付与するため、
> VLMには出させない（issues に使ってよいコードの一覧から外してある）。

### 3.3 ユーザープロンプト

```
【依頼内容】{task_description}
【撮影条件】{task_title}
【撮影地点の住所】{location_address}
【依頼者が希望した撮影日時】{scheduled_at}（日本時間）
【申告された撮影時刻】{captured_at}（日本時間）
【撮影時の時間帯】{period_of_day}
【参考画像の有無】あり | なし
【提出回数】{attempt_no}回目

{添付順の説明}

添付画像を検品し、JSONのみを出力してください。
```

**`【撮影時の時間帯】` は撮影時刻から機械的に決める**（日本時間の「時」で判定）。
「夜だから暗い」を不備と誤判定させないための材料。

| 時刻(JST) | 文言 |
|---|---|
| 7〜16時 | 日中（明るいことが期待される） |
| 16〜19時 | 夕方（薄暗いことが自然） |
| 5〜7時 | 早朝（薄暗いことが自然） |
| それ以外 | 夜間（暗いことが自然。照明で対象が判別できれば問題ない） |

参考画像がある場合、**1枚目を参考画像、2枚目を提出画像として送り**、プロンプトでその順序を明示する
（無い場合は `reference_match` を `null` にするよう指示する）。

**検品は原本（マスキング前）に対して行う。** 加工後の画像では判定材料が失われるため。

### 3.4 合否判定（サービス層）

```
score >= SUBMISSION_SCORE_THRESHOLD (60)
  かつ subject_present == true
  かつ location_check.within_tolerance == true
  かつ location_check.timestamp_consistent == true
→ approved
それ以外 → rejected
```

`subject_present == false` の場合は、スコアに関わらず不合格とする。
位置・時刻の不整合で不合格になった場合は、`issues` に `LOCATION_MISMATCH` / `TIMESTAMP_MISMATCH` を
サービス層で追加する。**合格した提出の `issues` は必ず空配列にする。**

### 3.5 境界だけ厚くする再判定（`_resolve_boundary()`）

`ORCA_VALIDATION_JURY` が設定されていて、かつ `|score − しきい値| ≤ ORCA_VALIDATION_BOUNDARY`（既定15）の
ときだけ、追加のモデルへ**並行**で問い合わせて多数決を取る。

- 票は「合格側か不合格側か」の2値で数える（`passes * 2 > len(votes)` で合格）。
- 採用するのは**多数派と同じ側を出した回答**。採点内容も多数派のものに揃える。
- 追加呼び出しが失敗しても、残った票で決める。

### 3.6 退化した応答の補正（サービス層）

VLM の出力そのものが壊れているケースを2つだけ機械的に直す。**どちらもログに警告を残す。**

| 補正 | 条件 | 処理 |
|---|---|---|
| `_repair_contradictory_score()` | `subject_present` と3つの品質フラグがすべて true、`issues` が空、**`observed_scene` と `summary` が両方とも空**、なのに `score < しきい値` | `score` をしきい値まで引き上げる |
| `_ignore_person_only_rejection()` | `subject_present` が true で、issues が `OTHER` / `OBSTRUCTED` だけ、かつ本文に「人物を避ける」趣旨の語が含まれる | `framing_ok=true` / `issues=[]` にし、`score` をしきい値以上へ、`summary` を `observed_scene` で置き換える |

前者は「本来11個あるキーが8個しか無い、途中で打ち切られたような出力」を実測したことによる。
プロンプトの採点基準に照らせば70点以上になるはずで、判定ではなく**出力の事故**である。
そのまま不合格にすると、問題の無い写真で再撮影を要求したうえに上限を1つ消費する。

> **低いスコアそのものを疑ってはいけない。** モデルが所見（`observed_scene` / `summary`）を
> 書いたうえで低く付けたのなら、それは根拠のある判定なので尊重する。
> 補正するのは**所見ごと欠落しているもの**に限る。

後者も同様に、対象が完全に隠れている本物のケースは
「人物を避ける」ではなく対象の視認不能を理由として返る前提で維持している。

---

## 4. 機能C: 位置偽装（Spoofing）対策

`app/services/location_check.py`。**LLM任せにせず、まず決定論的な計算を行う。**

### 4.1 チェック項目

| # | チェック | 方法 | 条件 | 影響 |
|---|---|---|---|---|
| C-1 | 距離検証 | 依頼地点と `captured_lat/lng` の Haversine距離 | `> LOCATION_TOLERANCE_METERS`(100m) | **合否に直結** |
| C-2 | 時刻整合 | `captured_at` と `received_at` の差 | `> TIMESTAMP_TOLERANCE_SECONDS`(300s) | **合否に直結** |
| C-3 | 撮影時間帯 | `scheduled_at` と `captured_at` の差 | `> ±6時間` | 減点のみ（−5） |
| C-4 | EXIF照合 | EXIFにGPSがある場合、申告座標との距離 | `> 200m` | 減点のみ（−20） |
| C-5 | 環境整合 | VLMの `daylight_state` と `captured_at` の時間帯 | 矛盾 | 減点のみ（−20） |
| C-6 | 精度チェック | `captured_accuracy_m` | `> 500m` | 減点のみ（−5） |

- **C-5 の日出没判定は外部APIを使わない。**「6時〜18時を daylight」という簡易判定
  （`method: "simple_hour_range_6_18"` として記録する）。
  `daylight_state` が `indoor` / `unknown` のときは判定不能として `consistent: null` にする。
- EXIFにGPSが**無いこと自体は不合格にしない**（ブラウザ撮影ではEXIFにGPSが入らないため）。
  C-4は「あれば照合する」補助チェックである（D-02）。
- EXIF の撮影時刻にタイムゾーン情報が無いため、**時刻の合否判定には使わない**（参考表示のみ）。

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

`within_tolerance`（C-1）と `timestamp_consistent`（C-2）は合否判定に直結する。それ以外は減点のみ。

保存される構造と `flags` のコード一覧は `docs/02-database.md` 2.5 を参照。

---

## 5. 機能D: プライバシー自動保護（D-09）

`app/services/masking.py`。**検品合格後にのみ実行**する（不合格画像は納品されないため処理不要）。

### 5.1 実装

- Ultralytics YOLO をローカル推論で使用する（クラウドVision APIは使わない）。
- 2モデル構成:
  - `YOLO_MODEL_PATH`（yolov8n.pt）: `person` / `car` / `truck` / `bus` / `motorcycle` を検出
  - `YOLO_FACE_MODEL_PATH`（yolov8n-face.pt）: 顔を直接検出
- 重みは `models_weights/` に配置する（`.gitignore` 対象。`scripts/download_yolo_models.py` で取得）。
- 一般モデルの推論は**1回だけ**行い、結果を人物と車両へ振り分ける。

**重みが無い環境での挙動**

| 状況 | 挙動 |
|---|---|
| YOLO の重みが無い ＆ **スタブモード** | 例外を出さずスキップし、`masking_result.skipped = true` と理由を記録して原本をそのまま返す |
| YOLO の重みが無い ＆ 実OrcaRouterが有効 | **VLM の座標検出だけで続行する**。`masking_result.yolo_skipped = true` を記録 |
| Ultralytics 自体が未導入 | 上と同じ扱い（`ImportError` を握りつぶす） |

デモを止めないための仕様。**スキップした場合は必ず警告ログを出す。**

### 5.2 マスキング対象と処理

| 対象 | 検出方法 | 処理 |
|---|---|---|
| 通行人の顔 | ローカルYOLO（face モデル） | ガウシアンぼかし。矩形を上下左右に**10%拡張** |
| 人物全体 | person クラス | **ぼかさない**（工事状況の確認に必要）。検出数だけ記録する |
| 車両 | car/truck/bus/motorcycle | ぼかさない。**プレート探索のヒント**としてVLMへ正規化座標を渡す |
| ナンバープレート | VLMへ座標を問い合わせる | **黒塗り**（完全マスク） |
| 表札・番地・書類 | VLMへ座標を問い合わせる | ガウシアンぼかし |

ナンバープレートと表札は軽量な物体検出モデルでは精度が出ないため、
**VLMに正規化座標（0〜1）で bbox を返させる。**

```python
class PrivacyRegion(BaseModel):
    kind: Literal["license_plate", "nameplate", "address_sign", "personal_document"]
    x1: float; y1: float; x2: float; y2: float   # 0.0〜1.0 の正規化座標
    confidence: float = 1.0
```

- **確信度 `MIN_REGION_CONFIDENCE`(0.3) 未満の領域は採用しない。**
- `x2 <= x1` / `y2 <= y1` のような不正な座標は警告ログを出して無視する。
- VLM呼び出しに失敗した場合も処理を止めず、YOLOで検出できた顔のみ処理する（`vlm_error` に記録）。
- ぼかし強度: 対象矩形の短辺 × `BLUR_KERNEL_RATIO`(0.15) をカーネルサイズとし、奇数に丸める。最小15px。
  Pillow は半径指定のため、カーネルサイズの半分を半径として使う。

**プロンプト**（`app/prompts/masking.py`）は「看板・案内表示・店名など、個人を特定しないものは
検出対象に含めない」ことを明示する。車両が検出されていれば、その正規化座標を
「ナンバープレートは車両領域の下部にあることが多い」というヒントとして添える。

### 5.3 保存

- 加工後画像を `STORAGE_BUCKET_PROCESSED` に保存し（品質90のJPEG）、`processed_image_url` に
  保存キー（`{taskId}/{assignmentId}/{attemptNo}.jpg`）を記録する。
- **原本は削除せず `STORAGE_BUCKET_RAW` に残すが、APIレスポンスには一切含めない**（争議時の証跡として保持する）。
- `masking_result` に処理内容を記録する。

```json
{
  "skipped": false,
  "regions": [
    { "kind": "face",          "method": "yolo_face", "bbox": [0.31,0.22,0.36,0.30], "blurred": true },
    { "kind": "license_plate", "method": "vlm",       "bbox": [0.55,0.61,0.64,0.65], "blurred": true }
  ],
  "face_count": 3,
  "person_count": 2,
  "vehicle_count": 1,
  "plate_count": 1,
  "processing_ms": 820
}
```

スキップ時は `skipped: true` / `reason` が入り、YOLOだけスキップした場合は
`yolo_skipped: true` / `yolo_skip_reason` が追加される。

---

## 6. 機能E: 投稿サムネイルの生成

一覧に並ぶ投稿は正方形の画像を持つ。写真が添付されていない依頼でも画像を用意する。

**段階的にフォールバックする**（`app/services/thumbnail_service.py`）

| 順 | 手段 | `thumbnail_source` |
|---|---|---|
| 1 | 依頼と一緒にアップロードされた参考画像の1枚目 | `reference` |
| 2 | ストリートビューをVLMで要約し、その説明から画像生成 | `generated` |
| 3 | ストリートビュー画像を正方形に切り抜く | `streetview` |
| 4 | サーバー側で描くプレースホルダ（外部API不要） | `placeholder` |

- 依頼が `open` になった直後に `BackgroundTasks` で実行する。**失敗しても依頼の公開は妨げない。**
- ストリートビューは Street View Static API（`GOOGLE_MAPS_SERVER_API_KEY`）。
  **まずメタデータ（課金対象外）でパノラマの有無とキーの有効性を確認してから**画像を取得する。
  一時的な失敗（タイムアウト・5xx・接続エラー・未知のstatus）だけ最大2回まで再試行し、
  `ZERO_RESULTS` / `NOT_FOUND` / `REQUEST_DENIED` / `INVALID_REQUEST` / `OVER_QUERY_LIMIT` は再試行しない。
- 画像生成のルーター名は `ORCA_ROUTER_IMAGE`。**未設定なら手順2を飛ばす。**
- 正方形化は **EXIF の回転情報を適用してから**中央を切り抜く（`to_square_jpeg()`）。
  スマホの写真は Orientation タグで回転を指示する形式が多く、無視すると横倒しになる。

プレースホルダは地点ピン・依頼タイトル・住所を描く。カード上では左上にタグ、左下に報酬が
重なるため、絵の要素は中央へ寄せる。日本語フォントが見つからない環境ではタイトルを描かず、
図形と座標だけで成立させる（豆腐を出さない）。背景色は依頼IDから決めて依頼ごとに変える。

**プロンプトの制約**（`app/prompts/thumbnail.py`）

- VLM には「実在の店名・看板の文字・人物の特徴・車両のナンバーに言及しない」ことを指示する。
- 画像生成には**イラスト調**であることを明示し、文字・ロゴ・顔・ナンバーを描かせない。
  実写と誤認され、現地の状況を示す証拠として扱われることを防ぐため。

> **未確認事項**: OrcaRouter の画像生成APIの正式な形式（エンドポイント・ルーター名）。
> 現状は OpenAI images 互換（`POST /images/generations`、`b64_json` または `url`）を想定して
> `OrcaClient.generate_image()` に実装している。判明したらこのメソッドの内部だけを差し替える。

サムネイルの意匠を変えたときは `python -m scripts.regenerate_thumbnails --force` で作り直す。

---

## 7. パイプライン統括

`app/services/submission_pipeline.py`。`POST /api/submissions` の BackgroundTasks から呼ばれる。

```
0. submissions.ai_validation_status = 'processing'（別セッションで即コミット）
1. 機能C（決定論的チェック C-1〜C-4, C-6）を実行
2. 機能B（VLM検品）を実行            ← 例外は伝播し、7. で error として記録
3. 機能C の C-5（環境整合）を B の daylight_state を用いて判定
4. reality_score を算出（ワーカーの trust_score も加味する）
5. 合否判定（3.4節）
   ├─ approved:
   │    5-1. 機能D（マスキング）を実行し、加工後画像を配信用バケットへ置く
   │    5-2. submissions を approved で更新
   │    5-3. assignment を approved、completed_at を設定
   │    5-4. tasks.approved_worker_count += 1
   │         required_worker_count に到達したら tasks.status='completed'
   │    5-5. ワーカーの trust_score +2.0、completed_task_count += 1
   │    5-6. payments に charge / payout を作成し stub_succeeded にする（D-03）
   │    5-7. ワーカーへ「合格」、充足したなら依頼者へ「完了」のお知らせを作成
   │    5-8. 合格済み提出の所見を集め、安全処理済み画像とともに
   │         OrcaRouter へ送って tasks.result_summary を生成
   └─ rejected:
        5-1. submissions を rejected で更新
        5-2. assignment.retake_count < MAX_RETAKE_COUNT なら
               retake_count += 1、assignment.status='accepted'（再撮影を許可）
               → ワーカーへ「再撮影」のお知らせ（残り回数つき）
             そうでなければ
               assignment.status='failed'、completed_at を設定、trust_score −5.0
               → ワーカーへ「受注キャンセル」のお知らせ
               → 有効な受注が0件で期限内なら tasks を open へ戻す（D-08）
6. 例外発生時は ai_validation_status='error' とし、assignment を 'accepted' に戻す
   （**retake_count は増やさない**。ワーカーの責任ではないため）
```

**5. までのDB更新は単一トランザクションで行い、失敗時はロールバックする。**
`ai_invocations` への記録だけは独立セッションのため残る（1.4）。
Storage への書き込みはトランザクション外のため、失敗時は孤児ファイルが残る。許容する（削除処理は実装しない）。

### 7.1 クライアント向け総括（`result_summary.py`）

合格時に、**安全処理済みの画像**と、それまでの合格提出の個別所見（`ai_feedback.summary`）を
OrcaRouter へ渡して `tasks.result_summary` を生成する。

プロンプトの要点（`app/prompts/result_summary.py`）:

- **依頼者が知りたかったことに答える。** 画像の説明ではなく、依頼への回答を書く。
- 画像から実際に確認できる事実だけを書く。
- 「予定どおり」「安全である」「問題ない」など、**画像だけでは断定できない評価を書かない**
  （比較対象や基準が与えられていないため）。
- 確認できなかった点は正直に書く。一般論や推測で字数を埋めない。
- 120文字以内。

### 7.2 依頼文の下書き生成（`task_description.py`）

画面①の「AIで詳細を作成」。`max_tokens=800` を明示的に渡している。
**300 では推論モデルへ振られたときに reasoning tokens だけで使い切り、本文が空になる**
（実測: `orcarouter/auto` と gemini 系で 8件中 7〜8件が `finish_reason="length"`）。
生成する文は180文字以内なので、800 でも通常の出力量は変わらない。

出力は 10〜180文字の `description` 1項目のみ。
「タイトルから分からない住所・日時・固有名詞・事実を捏造しない」「個人の監視、住居の防犯確認、
危険な立入りを促す内容にしない」ことをプロンプトで明示する。生成後もユーザーが自由に編集できる。
