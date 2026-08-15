# 04. AIパイプライン仕様

本プロダクトの中核。以下の4機能を実装する。

| # | 機能 | 実行タイミング | 使用モデル |
|---|---|---|---|
| A | 依頼コンテキスト審査 | 依頼作成時（同期） | 軽量LLM |
| B | VLMによる画像検品 | 画像提出後（非同期） | VLM |
| C | 位置偽装対策 | 画像提出後（非同期） | 計算＋VLM |
| D | プライバシー自動保護 | 検品合格後（非同期） | ローカルYOLO |
| E | 投稿サムネイルの生成 | 依頼公開後（非同期） | VLM＋画像生成 |

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

`response_format: {"type": "json_object"}` はアップストリームのモデルによって対応状況が異なる。

> **実装では `response_format: {"type": "json_schema"}` を送っている。**
> 指示を無視してJSON以外を返すモデルが実在したため、形はAPIに強制させる。
> ただし **Pydantic の `model_json_schema()` をそのまま渡してはならない。**
> アップストリームごとに要求が違い、実測で次の 400 が返った。
> 400 はリトライされないため、踏むとその用途が丸ごと落ちる。
>
> | アップストリーム | 400 の理由 |
> |---|---|
> | Anthropic 系 | `object` に `additionalProperties: false` が明示されていない |
> | Gemini 系 | `$defs` / `$ref` を解釈できない（入れ子のモデルを持つスキーマで発生） |
>
> `orca_client._normalize_schema()` が `$ref` を実体へ展開し、
> すべての `object` に `additionalProperties: false` を付けて両方の制約を満たす。
> **スキーマに入れ子のモデルを増やしたときは、実モデルへ1回投げて確認すること。**

以下の順で対処する。

1. `response_format` で形を指定しつつ、プロンプトでも「JSONのみを出力」と厳命する。
2. レスポンスからコードフェンス（```json ... ```）と前後の空白を除去する。
3. 先頭の `{` から対応する末尾の `}` までを抽出してパースする（前置きの文章が付いた場合の救済）。
4. それでも失敗したら、`messages` に「直前の出力はJSONとして解析できませんでした。説明を含めず、JSONオブジェクトのみを出力してください。」を追加して再試行する。

**ルーター構成（改訂）**

当初は `ORCA_ROUTER_LIGHT` / `ORCA_ROUTER_VISION` のどちらにも `orcarouter/auto` を設定して1つのルーターで運用していたが、**実測の結果これをやめ、tier の既定にも具体的なモデルを置く。**

`orcarouter/auto` は呼び出しごとに振り先が変わる（同じプロンプトで `qwen3.7-plus` と `deepseek-v4-pro` の両方を観測した）。推論モデルへ当たると reasoning tokens だけで `max_tokens` を使い切り、`finish_reason="length"` で**本文が空**のまま返る。依頼文生成（`max_tokens=300`）では8件中7件がこれで失敗した。

| 環境変数 | 値 | 理由 |
|---|---|---|
| `ORCA_ROUTER_LIGHT` | `openai/gpt-5.4-mini` | 推論に予算を取られない。実測1.4秒で8/8成功 |
| `ORCA_ROUTER_VISION` | `qwen/qwen3-vl-235b-a22b-instruct` | Vision非対応へ振られる事故が起きない |

ただし `orcarouter/auto` は全モデルを許可しているため、画像付きリクエストで Vision 非対応のモデルへルーティングされる可能性がある。**画像付き呼び出しで 400 系エラーやモデル非対応のエラーが返った場合は、リトライで解決しないため作業を止めて人間に報告すること**（Vision対応モデルのみを許可した専用ルーターを作成して `ORCA_ROUTER_VISION` に設定する対処が必要になる）。この場合もコード変更は不要で、環境変数の差し替えのみで解決できる設計にしておくこと。

**エラー時のHTTPステータス**

| ステータス | 対処 |
|---|---|
| 401 / 403 | リトライせず即座に `AIServiceError`。APIキー設定ミスの可能性をログに明記 |
| 429 | 指数バックオフでリトライ（`Retry-After` ヘッダがあれば優先） |
| 5xx / タイムアウト | 指数バックオフでリトライ |
| 400 | リトライせず `AIServiceError`。リクエストボディをログに残す（画像は除く） |

### 1.2 モデルの振り分け（用途 × リスク）

**分類軸は「画像の有無」ではなく「間違えたときの損失」。**
画像の有無で分けると、中核の検品と飾りのサムネイルが同じ扱いになってしまう。

| 段階 | 間違えると何が起きるか | 該当するプロンプト |
|---|---|---|
| S: 取り返しがつかない | 犯罪の幇助・不当な失格・個人情報の公開 | 依頼審査 / **画像検品** / マスキング座標 |
| A: 品質に響くが回復可能 | 納品文が的外れ | 調査結果の総括 |
| B: やり直しが効く | 見た目が少し悪い | 詳細メッセージ生成 / サムネイル情景説明 |

用途ごとに環境変数でモデルを指定する。未設定なら `ORCA_ROUTER_LIGHT` /
`ORCA_ROUTER_VISION` の既定へ落ちる。

| 環境変数 | 用途 | `model_key` |
|---|---|---|
| `ORCA_MODEL_TASK_REVIEW` | 依頼審査 | `task_review` |
| `ORCA_MODEL_IMAGE_VALIDATION` | 画像検品 | `image_validation` |
| `ORCA_MODEL_MASKING` | マスキング座標 | `masking` |
| `ORCA_MODEL_RESULT_SUMMARY` | 調査結果の総括 | `result_summary` |
| `ORCA_MODEL_TASK_DESCRIPTION` | 詳細メッセージ生成 | `task_description` |
| `ORCA_MODEL_THUMBNAIL` | サムネイル情景説明 | `thumbnail` |

> **`orcarouter/auto` を重要な用途に使わない。**
> 中身は予告なく変わる（仕様書が「既定は grok/grok-4.5」と書いていた時期に、
> 実体は `qwen3.7-plus` だった）。品質が落ちても気づけないため、明示指定する。

実測にもとづく現在の割り当ては次のとおり。数字は `scripts/bench_task_review.py`
（正当14件＋悪意8件）と `scripts/bench_models.py`（実写真5ケース）の結果。

| 用途 | モデル | 実測 |
|---|---|---|
| 依頼審査 | `anthropic/claude-opus-5` | 正当14/14・悪意8/8。まれにJSON破損があるため合議で吸収する |
| 画像検品 | `anthropic/claude-opus-5` | 5/5・ブレ0。合格側スコアの余裕が **+18** で最大（5.9秒） |
| 詳細メッセージ生成 | `openai/gpt-5.4-mini` | 8/8成功・1.4秒。`openai/gpt-5-mini` は推論に予算を使い切り **0/4** |

> **検品モデルは「正答率」だけで選ばない。**
> `claude-haiku-4.5` は5/5正答だが、合格すべき写真のスコアが 72〜75 と
> しきい値70の**わずか+2**しかない。振れ幅を考えると、まともな写真が再撮影になる。
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
2回とも一致した。待っているのは現地のワーカーなので、待ち時間を一律3倍にする
価値はない。

票が同数のときは `rejected > needs_info > approved` の順に**慎重な側**を採る。
公開してからでは取り返しがつかないためだが、**この非対称性は無条件ではない。**
`rejected` は行き止まりで、依頼者は書き直して再申請できない
（`task_service.resubmit_task` は `NEEDS_INFO` の依頼しか受け付けない）。
誤った却下はそのまま失注になる。

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

- `bench_models` … 実写真11ケースについて、合否・被写体の有無が模範解答と一致するか、
  2回流して合否が割れないか、何秒かかるかを表で出す。
  うち6ケースは**現地の粗い写真**（暗い / 真っ暗に近い / 手ブレ / 隅に寄る / 傾き / 遠い /
  夜間＋手ブレ）を加工で再現したもので、**すべて合格すべきもの**として置いてある。
  ここが落ちる状態は「ワーカーが達成できない検品」になっている合図。
- `bench_task_review` … 正当な依頼14件（**依頼文生成AIの実出力**を使う）と明らかに黒い依頼8件を、
  `content_filter` → 審査プロンプトの順に本番と同じ経路で通す。
  `--combo a,b,c` を付けると `ORCA_MODEL_TASK_REVIEW` ＋ `ORCA_REVIEW_JURY` の
  多数決そのものを評価できる。**見るべき指標は「誤却下」**（正当な依頼を却下した数）。

### 1.3 インターフェース定義

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

### 1.4 実装要件

- `tier="light"` は `ORCA_ROUTER_LIGHT`、`tier="vision"` は `ORCA_ROUTER_VISION` の値を `model` に設定する。どちらも既定値は `orcarouter/auto`。
- **リトライ**: 429・5xx・タイムアウト・JSONパース失敗時に `ORCA_MAX_RETRIES` 回まで指数バックオフ（1s, 2s）で再試行する。401/403/400 はリトライしない。
- **JSON強制**: 上記1.1「JSON出力の扱い」の4段階に従う。
- パース結果は必ず `response_schema` で Pydantic バリデートする。失敗したらリトライ扱いとし、最終的に失敗したら `AIServiceError` を送出する。
- `httpx.AsyncClient` はアプリのライフサイクルで使い回す（リクエストごとに生成しない）。タイムアウトは `ORCA_TIMEOUT_SECONDS`。
- 全呼び出しについて `ai_invocations` にログを記録する。**画像のbase64は保存せず、URLまたは `"<image omitted>"` に置換する。**
- 呼び出しが最終的に失敗したら `AIServiceError` を送出する。

### 1.5 スタブモード（必須）

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

### 2.2.1 AIより前に通す決定論フィルタ（`app/services/content_filter.py`）

**LLMを呼ぶ前に、キーワードによる安全審査を必ず通す。** 該当したらAIを呼ばずに `rejected` で確定する。

理由は2つ。

1. **スタブモード（`ORCA_STUB_MODE=true`）ではLLMを呼ばない。** 本番のデモ環境はこの設定で
   動いており、AI側の審査が丸ごと素通りする。フィルタが無いと、犯罪目的の依頼がそのまま公開される
2. 実運用でもLLMは指示を無視することがある。取り返しのつかない却下漏れを防ぐ多層防御

判定は2種類。

| 種類 | 例 | 考え方 |
|---|---|---|
| 単語1つで却下 | 盗撮 / ストーカー / 空き巣 / 侵入経路 / 忍び込む | 言い逃れの余地が無いもの |
| 2語の共起で却下 | 「施錠」＋「侵入」、「行動パターン」＋「元カノ」 | 片方だけでは正当な依頼を巻き込むため |

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

検査前に NFKC 正規化して空白を除く。「盗 撮」「ｽﾄｰｶｰ」のような小細工をすり抜けさせない。

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

> **合格の基準は「きれいに撮れているか」ではなく「依頼者が判断できるか」。**
> 当初の配点（対象40 / 構図20 / ピント20 / 明るさ20）では、**構図と写りの良さで60点**を占め、
> 対象が写っていても粗ければ落ちる。実測でも、ブレた写真が 72点（しきい値70に対し **+2**）と
> 合否の境目に張り付き、`TOO_BLURRY` が付いていた。
> 現地で1枚撮るだけのワーカーには達成が難しく、再撮影の上限（2回）を超えると受注が取り消される。
>
> 配点を「対象が写っている60 / 状態が読み取れる25 / 構図10 / 明るさ5」に組み替え、
> 傾き・端寄り・軽いブレ・暗さを減点理由から外した。**対象の有無（`subject_present`）と
> 位置・時刻の検証は緩めていない**（3.4）。顔・ナンバープレートの扱いも変更していない。
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

【構図・鮮明さの判定 framing_ok / sharpness_ok】
対象が画面に収まっており、何が写っているか分かるなら framing_ok は true にしてください。
中央から外れている、傾いている、余白が多い、といった理由で false にしてはいけません。
sharpness_ok も同様に、**対象の形と状態が読み取れるなら true** です。

【第三者・顔の扱い】
- 通行人や利用者の顔・人物が写っていること自体は不合格要素ではありません。検品合格後のマスキング処理で保護します。
- 顔や人物の存在だけを理由に score を下げたり、各判定を false にしたり、issues を追加したりしてはいけません。
- 行列・混雑・利用状況など人物を含む光景が依頼対象の場合、人物が写っていることを依頼条件への適合として評価してください。
- 人物によって依頼対象が判別不能なほど完全に隠れている場合に限り、OBSTRUCTED を使用できます。

VLMが上記に反して、対象を確認できているにもかかわらず人物・顔の回避だけを理由に
`OTHER` / `OBSTRUCTED` を返した場合、サービス層でそのissueを除外し、人物の存在による
`framing_ok` とスコアの減点を補正する。対象物の不足、暗さ、ブレなど人物以外の問題は補正しない。

【issues】**再撮影させなければ依頼が果たせない場合のみ**記述し、それ以外は必ず空配列にしてください。
対象が判別できるのに TOO_DARK / TOO_BLURRY / ANGLE_MISMATCH / TOO_FAR を付けることは誤りです。
「もっとこう撮ればより良い」という助言を issues に書いてはいけません。
記述するときは、ワーカーが次に何をすべきかが分かる日本語の短い指示（30文字以内）にしてください。

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
score >= SUBMISSION_SCORE_THRESHOLD (60)
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

---

## 5. 機能E: 投稿サムネイルの生成

一覧に並ぶ投稿は正方形の画像を持つ。写真が添付されていない依頼でも画像を用意する。

**段階的にフォールバックする**（`app/services/thumbnail_service.py`）

| 順 | 手段 | `thumbnail_source` |
|---|---|---|
| 1 | 依頼と一緒にアップロードされた参考画像の1枚目 | `reference` |
| 2 | ストリートビューをVLMで要約し、その説明から画像生成 | `generated` |
| 3 | ストリートビュー画像を正方形に切り抜く | `streetview` |
| 4 | サーバー側で描くプレースホルダ（外部API不要） | `placeholder` |

プレースホルダは地点ピン・依頼タイトル・住所を描く。カード上では左上にタグ、左下に報酬が
重なるため、絵の要素は中央へ寄せる。日本語フォントが見つからない環境ではタイトルを描かず、
図形と座標だけで成立させる（豆腐を出さない）。

- 依頼が `open` になった直後に `BackgroundTasks` で実行する。**失敗しても依頼の公開は妨げない。**
- ストリートビューは Street View Static API（`GOOGLE_MAPS_SERVER_API_KEY`）。
  まずメタデータ（課金対象外）でパノラマの有無を確認してから画像を取得する。
- 画像生成のルーター名は `ORCA_ROUTER_IMAGE`。**未設定なら手順2を飛ばす。**

**プロンプトの制約**（`app/prompts/thumbnail.py`）

- VLM には「実在の店名・看板の文字・人物の特徴・車両のナンバーに言及しない」ことを指示する。
- 画像生成には**イラスト調**であることを明示し、文字・ロゴ・顔・ナンバーを描かせない。
  実写と誤認され、現地の状況を示す証拠として扱われることを防ぐため。

> **未確認事項**: OrcaRouter の画像生成APIの正式な形式（エンドポイント・ルーター名）。
> 現状は OpenAI images 互換（`POST /images/generations`、`b64_json` または `url`）を想定して
> `OrcaClient.generate_image()` に実装している。判明したらこのメソッドの内部だけを差し替える。
