# 02. データベース設計

DB: PostgreSQL（Supabase、またはローカル `docker compose up -d db`）。マイグレーションは Alembic で管理する。
すべての主キーは `uuid`（`gen_random_uuid()`）、時刻は `timestamptz`（UTC保存）とする。

**このドキュメントは `backend/app/models/` の実装と1対1で対応する。**
スキーマの破壊的変更（カラム削除・型変更）が必要になったら、実装前に人間へ確認する（`CLAUDE.md` 3節）。

---

## 0. マイグレーションの系譜

```
3237be2160d3  create_initial_schema
     └─ 8f2a41c7d9b3  add_login_credentials_and_drop_role   （D-06。users.role を削除）
            └─ 57748aa07b1d  add_likes_saved_searches_view_count_and_thumbnail
                   ├─ 1938a8d17ebf  add_notifications
                   └─ a21c8e34f901  add_worker_reviews
                          └─ 335d3aa1b952  merge_notifications_and_worker_reviews
                                 └─ 78cfaa231369  add_min_worker_rating_to_tasks   ← head
```

```bash
cd backend && ./.venv/bin/alembic upgrade head
cd backend && ./.venv/bin/alembic revision --autogenerate -m "message"
```

> `autogenerate` は `app/models/__init__.py` で import されたモデルしか検出しない。
> 新しいモデルを足したら必ずそこへ追記する。

---

## 1. ENUM定義

```sql
CREATE TYPE task_status        AS ENUM ('screening', 'rejected', 'needs_info', 'open', 'in_progress', 'completed', 'expired', 'cancelled');
CREATE TYPE assignment_status  AS ENUM ('accepted', 'submitted', 'approved', 'failed', 'cancelled', 'expired');
CREATE TYPE validation_status  AS ENUM ('pending', 'processing', 'approved', 'rejected', 'error');
CREATE TYPE payment_direction  AS ENUM ('charge', 'payout');
CREATE TYPE payment_status     AS ENUM ('stub_pending', 'stub_succeeded', 'stub_failed');
CREATE TYPE notification_type  AS ENUM ('task_approved', 'task_needs_info', 'task_rejected', 'task_accepted',
                                        'submission_approved', 'submission_retake', 'submission_failed',
                                        'task_completed', 'task_expired');
```

Python 側は `app/models/enums.py`。ラベルを変えるとマイグレーションが要るため、勝手に変えない。

同じファイルに、**アプリ側で意味を持つ2つの集合**を定数として置いている。

| 定数 | 中身 | 用途 |
|---|---|---|
| `ACTIVE_ASSIGNMENT_STATUSES` | `accepted` / `submitted` / `approved` | 受注枠を占有している状態。`failed` / `cancelled` / `expired` は含めないため、枠が自動で再開放される（D-08） |
| `PUBLIC_TASK_STATUSES` | `open` / `in_progress` / `completed` / `expired` / `cancelled` | 一度でも掲示板に公開された依頼。公開プロフィールの統計の母数（`screening` / `needs_info` / `rejected` は含めない） |

---

## 2. テーブル定義

全10テーブル。`app/models/` の各ファイルと対応する。

### 2.1 users （`app/models/user.py`）

ログインID＋パスワードで認証する（D-06）。**ロールは持たない**。
1つのアカウントで「依頼する」「撮影する」の両方を行える。

| カラム | 型 | 制約 | 説明 |
|---|---|---|---|
| id | uuid | PK | |
| login_id | text | NOT NULL UNIQUE, INDEX | ログインID。半角英数字とアンダースコア3〜32文字 |
| password_hash | text | NOT NULL | bcrypt ハッシュ。平文は保存しない |
| display_name | text | NOT NULL | 表示名（相手に見える名前） |
| email | text | UNIQUE | 任意。デモ用のダミーで可 |
| trust_score | numeric(4,1) | NOT NULL DEFAULT 50.0 | 0〜100。撮影者としての信頼度 |
| completed_task_count | int | NOT NULL DEFAULT 0 | 承認された提出の累計 |
| avatar_url | text | | **保存キーのみ**（配信URLは持たない。3.0.1 参照） |
| created_at | timestamptz | NOT NULL DEFAULT now() | |

**trust_score の更新ルール**（`apply_trust_score_delta()`）
- 検品合格（`approved`）: **+2.0**
- 再撮影上限超過による失格（`failed`）: **−5.0**
- 上下限は 0〜100 でクリップする。

> `avatar_url` に入るのは `user-avatar/{user_id}/{画像のハッシュ}.jpg` という保存キーで、
> **加工済みバケット側**に置く。原本バケットは提出画像の原本専用。

---

### 2.2 tasks （`app/models/task.py`）

| カラム | 型 | 制約 | 説明 |
|---|---|---|---|
| id | uuid | PK | |
| client_id | uuid | FK→users.id, NOT NULL | |
| title | text | NOT NULL | 依頼タイトル（API側で1〜60文字） |
| description | text | NOT NULL | 詳細メッセージ（API側で10〜1000文字） |
| location_lat | double precision | NOT NULL | 依頼地点の緯度 |
| location_lng | double precision | NOT NULL | 依頼地点の経度 |
| location_address | text | | 逆ジオコーディング結果 |
| scheduled_at | timestamptz | NOT NULL | 撮影してほしい日時 |
| deadline_at | timestamptz | NOT NULL | この時刻を過ぎたら掲示板から外す（`expired`） |
| reward_amount | int | NOT NULL, CHECK > 0 | 1人あたりの報酬（円）。API側で100〜100000 |
| required_worker_count | int | NOT NULL DEFAULT 1, CHECK BETWEEN 1 AND 10 | 撮影人数（D-05） |
| approved_worker_count | int | NOT NULL DEFAULT 0 | 検品合格済み人数 |
| min_worker_rating | double precision | CHECK NULL または 1.0〜5.0 | 受注できるワーカーの最低平均評価。NULL なら条件なし |
| status | task_status | NOT NULL DEFAULT 'screening' | |
| review_score | int | | AI審査の十分性スコア 0〜100 |
| review_summary | text | | AI生成の依頼要約（画面③に表示） |
| review_feedback | jsonb | | 判定・チェック項目・不足情報・却下理由（下記） |
| result_summary | text | | 合格画像を踏まえたAI総括（画面⑨⑩に表示） |
| thumbnail_image_url | text | | 正方形サムネイルの保存キー（配信用バケット）。未生成なら NULL |
| thumbnail_source | text | | `reference` / `generated` / `streetview` / `placeholder` |
| view_count | int | NOT NULL DEFAULT 0 | 詳細を開かれた回数。HOTタグの判定に使う |
| like_count | int | NOT NULL DEFAULT 0 | `task_likes` の集計値（一覧のN+1を避ける非正規化） |
| created_at | timestamptz | NOT NULL DEFAULT now() | |
| updated_at | timestamptz | NOT NULL DEFAULT now(), onupdate now() | |

**インデックス**
```sql
CREATE INDEX idx_tasks_status_deadline ON tasks (status, deadline_at);
CREATE INDEX idx_tasks_location        ON tasks (location_lat, location_lng);
CREATE INDEX idx_tasks_client          ON tasks (client_id, created_at DESC);
```

> 近傍検索はバウンディングボックス（`idx_tasks_location`）で粗く絞り、
> アプリ側の Haversine で正確な距離を出す。**PostGISは導入しない。**

**`review_feedback` の構造**

```json
{
  "decision": "needs_info",
  "checks": { "safety": "pass", "validity": "pass", "risk": "pass", "duplication": "pass" },
  "missingInfo": ["撮影してほしいアングル（正面／側面）を指定してください"],
  "rejectionReason": null,
  "llmDecision": "approved"
}
```

`llmDecision` は LLM が返した生の判定。**最終判定（`decision`）はサービス層が決める**ため、
両者が食い違うことがある。監査のために両方残している（`docs/04-ai-pipeline.md` 2.3）。

**閲覧数のカウント規則**: `GET /api/tasks/{id}` で**オーナー以外**が開いたときだけ +1 する。
自分の依頼を自分で開いた分は HOT タグに影響しない。

---

### 2.3 task_reference_images （`app/models/task.py`）

クライアントが「期待する画像イメージ」としてアップロードする参考画像。

| カラム | 型 | 制約 | 説明 |
|---|---|---|---|
| id | uuid | PK | |
| task_id | uuid | FK→tasks.id ON DELETE CASCADE, NOT NULL | |
| image_url | text | NOT NULL | **加工済みバケット**内の保存キー |
| sort_order | int | NOT NULL DEFAULT 0 | |
| created_at | timestamptz | NOT NULL DEFAULT now() | |

- 上限は1依頼あたり**3枚**（`MAX_REFERENCE_IMAGES`）。
- 保存先が加工済みバケットなのは、**ワーカーに見せる画像だから**。原本バケットは提出画像の原本専用。
- 依頼の複製（`POST /api/tasks/{id}/duplicate`）では画像を再アップロードせず、**同じ保存キーを共有する**。

---

### 2.4 task_assignments （`app/models/task_assignment.py`）

ワーカーの受注枠。1依頼につき最大 `required_worker_count` 件まで**有効な**枠を持てる。

| カラム | 型 | 制約 | 説明 |
|---|---|---|---|
| id | uuid | PK | |
| task_id | uuid | FK→tasks.id, NOT NULL | |
| worker_id | uuid | FK→users.id, NOT NULL | |
| status | assignment_status | NOT NULL DEFAULT 'accepted' | |
| retake_count | int | NOT NULL DEFAULT 0 | 再撮影を指示した回数（0〜`MAX_RETAKE_COUNT`） |
| accepted_at | timestamptz | NOT NULL DEFAULT now() | |
| completed_at | timestamptz | | approved / failed / cancelled / expired になった時刻 |

**制約**
```sql
ALTER TABLE task_assignments ADD CONSTRAINT uq_assignment_task_worker UNIQUE (task_id, worker_id);
```

**受注時の同時実行制御（必須）**

受注枠の超過を防ぐため、`POST /api/tasks/{id}/accept` は以下をひとつのトランザクションで行う
（`task_repo.get_for_update()` → `assignment_repo.count_active()`）。

```sql
SELECT ... FROM tasks WHERE id = :task_id FOR UPDATE;
-- 有効枠 = required_worker_count
-- 使用中 = COUNT(assignments WHERE status IN ('accepted','submitted','approved'))
-- 使用中 >= 有効枠 なら 409 TASK_FULL
```

**辞退と受け直し**

`(task_id, worker_id)` に一意制約があるため、辞退（`cancelled`）したワーカーが受け直すときは
**新しい行を作らず既存行を `accepted` へ戻す**（`assignment_repo.reactivate()`）。
このとき **`retake_count` は引き継ぐ**。引き継がないと、辞退→受け直しで再撮影の上限（D-08）を
リセットできてしまうため。

---

### 2.5 submissions （`app/models/submission.py`）

ワーカーの提出物。1つの assignment に対して最大3件（初回＋再撮影2回）作られる。

| カラム | 型 | 制約 | 説明 |
|---|---|---|---|
| id | uuid | PK | |
| assignment_id | uuid | FK→task_assignments.id, NOT NULL | |
| task_id | uuid | FK→tasks.id, NOT NULL | 検索用の非正規化 |
| worker_id | uuid | FK→users.id, NOT NULL | 同上 |
| attempt_no | int | NOT NULL | 1〜3 |
| raw_image_url | text | NOT NULL | **原本。クライアントには絶対に返さない** |
| processed_image_url | text | | マスキング済み画像の保存キー |
| captured_lat | double precision | NOT NULL | 撮影時のデバイス位置（D-02） |
| captured_lng | double precision | NOT NULL | 同上 |
| captured_accuracy_m | double precision | | Geolocation APIの精度 |
| captured_at | timestamptz | NOT NULL | 端末側の撮影時刻（D-02） |
| received_at | timestamptz | NOT NULL DEFAULT now() | サーバー受信時刻 |
| device_info | jsonb | | userAgent, プラットフォーム, 画面サイズ, `captureMode` |
| exif_data | jsonb | | 抽出できたEXIF（補助検証用） |
| ai_validation_status | validation_status | NOT NULL DEFAULT 'pending' | |
| ai_score | int | | 検品スコア 0〜100 |
| ai_feedback | jsonb | | チェック結果・再撮影指示・要約（下記） |
| location_check | jsonb | | 位置整合チェックの結果（下記） |
| masking_result | jsonb | | 検出・処理した領域の情報（`docs/04-ai-pipeline.md` 5.3） |
| reality_score | int | | 信頼度スコア 0〜100（画面⑨⑩に表示） |
| created_at | timestamptz | NOT NULL DEFAULT now() | |

**制約**
```sql
ALTER TABLE submissions ADD CONSTRAINT uq_submission_attempt UNIQUE (assignment_id, attempt_no);
ALTER TABLE submissions ADD CONSTRAINT ck_attempt_no CHECK (attempt_no BETWEEN 1 AND 3);
CREATE INDEX idx_submissions_task ON submissions (task_id, created_at DESC);
```

**`location_check` の構造**（`location_check.run_deterministic_checks()` の戻り値そのまま）

```json
{
  "distance_m": 42.5,
  "within_tolerance": true,
  "timestamp_delta_seconds": 63,
  "timestamp_consistent": true,
  "schedule_delta_seconds": 1800,
  "schedule_within_window": true,
  "exif_gps_present": true,
  "exif_gps_conflict": false,
  "exif_gps_distance_m": 18.2,
  "exif_datetime": "2026-05-28T13:42:00",
  "accuracy_m": 12.0,
  "accuracy_ok": true,
  "environment_consistency": {
    "expected_daylight": true,
    "observed_daylight": true,
    "daylight_state": "daylight",
    "consistent": true,
    "note": "画像内の光の状態は撮影時刻と矛盾しない",
    "method": "simple_hour_range_6_18"
  },
  "flags": []
}
```

`flags` に入りうるコード:
`DISTANCE_EXCEEDED` / `TIMESTAMP_DRIFT` / `SCHEDULE_DRIFT` / `EXIF_GPS_CONFLICT` / `LOW_ACCURACY` / `ENVIRONMENT_MISMATCH`

`environment_consistency` は VLM 検品（機能B）の出力を使うため、決定論チェックの時点では `null`。
検品後に `apply_environment_check()` が埋める。`consistent` は `true` / `false` / `null`（判定不能）の3値。

**`ai_feedback` の構造**

```json
{
  "checks": {
    "subject_present": true,
    "framing_ok": true,
    "sharpness_ok": false,
    "brightness_ok": true
  },
  "issues": [
    { "code": "ANGLE_MISMATCH", "message": "対象を中央に収めて撮り直してください" }
  ],
  "summary": "看板は写っていますが、画角から一部が外れています。"
}
```

- **合格した提出の `issues` は必ず空配列にする**（サービス層で落とす）。
- `issues[].code` は画面⑧が固定文言を出せるよう、以下の定義済みコードのみを使う。
  `SUBJECT_MISSING` / `TOO_DARK` / `TOO_BLURRY` / `ANGLE_MISMATCH` / `TOO_FAR` / `OBSTRUCTED` /
  `LOCATION_MISMATCH` / `TIMESTAMP_MISMATCH` / `OTHER`
- `LOCATION_MISMATCH` / `TIMESTAMP_MISMATCH` は VLM ではなく**サービス層が付与する**。

---

### 2.6 payments （スタブ / D-03）（`app/models/payment.py`）

実決済は行わない。取引の記録のみを残す。

| カラム | 型 | 制約 | 説明 |
|---|---|---|---|
| id | uuid | PK | |
| task_id | uuid | FK→tasks.id, NOT NULL | |
| submission_id | uuid | FK→submissions.id | 支払いの根拠となった提出 |
| user_id | uuid | FK→users.id, NOT NULL | 課金先または支払先 |
| direction | payment_direction | NOT NULL | charge=クライアント課金 / payout=ワーカー支払い |
| amount | int | NOT NULL | 円 |
| status | payment_status | NOT NULL DEFAULT 'stub_pending' | |
| processed_at | timestamptz | | |
| created_at | timestamptz | NOT NULL DEFAULT now() | |

検品合格時に `charge` と `payout` を1件ずつ作成し、**即座に `stub_succeeded`** にする
（`payment_stub.record_settlement()`）。金額はどちらも `tasks.reward_amount`。

**外部決済SDKの導入・カード番号や口座番号の保存は行わない。**

---

### 2.7 ai_invocations （`app/models/ai_invocation.py`）

AI呼び出しの監査ログ。デバッグとデモでの説明に使う。

| カラム | 型 | 説明 |
|---|---|---|
| id | uuid | PK |
| purpose | text | `task_review` / `task_description_generation` / `image_validation` / `environment_check` / `result_summary` / `thumbnail_generation` |
| related_type | text | `task` / `submission` / `task_draft` |
| related_id | uuid | 対象レコードのID（下書き段階では NULL） |
| model | text | 実際に使われたモデル名（OrcaRouterの応答の `model`）。スタブ時は `"stub"` |
| request_payload | jsonb | プロンプト・tier・model・max_tokens など。**画像はURLか `"<image omitted>"` に置換**（base64は保存しない） |
| response_payload | jsonb | 生レスポンス（`usage` を含む） |
| latency_ms | int | |
| is_stub | boolean | NOT NULL DEFAULT false |
| error | text | 失敗した場合の理由 |
| created_at | timestamptz | NOT NULL DEFAULT now() |

> 記録は `ai_invocation_repo.create_autonomous()` を通し、**独立したセッションでコミットする**。
> 業務トランザクションがロールバックしても監査ログだけは残る。

---

### 2.8 notifications （`app/models/notification.py`）

お知らせ（下部タブ）。ステータス遷移に連動して `notification_service.notify()` が作る。

| カラム | 型 | 制約 | 説明 |
|---|---|---|---|
| id | uuid | PK | |
| user_id | uuid | FK→users.id ON DELETE CASCADE, NOT NULL | 宛先 |
| type | notification_type | NOT NULL | |
| title | text | NOT NULL | 一覧に太字で出す見出し |
| body | text | | 補足（不足情報の一覧・却下理由・残り再撮影回数など） |
| task_id | uuid | FK→tasks.id ON DELETE CASCADE | 遷移先の決定に使う |
| submission_id | uuid | FK→submissions.id ON DELETE CASCADE | 提出系の通知で検品結果へ飛ばすために使う |
| read_at | timestamptz | | NULL なら未読 |
| created_at | timestamptz | NOT NULL DEFAULT now() | |

```sql
CREATE INDEX idx_notifications_user ON notifications (user_id, created_at DESC);
```

**発火する場所**

| type | 宛先 | 発火元 |
|---|---|---|
| `task_approved` / `task_needs_info` / `task_rejected` | 依頼者 | `task_review._notify_review_result()` |
| `task_accepted` | 依頼者 | `task_service.accept_task()` |
| `submission_approved` | ワーカー | `submission_pipeline._handle_approved()` |
| `submission_retake` | ワーカー | `submission_pipeline._handle_rejected()`（上限未満） |
| `submission_failed` | ワーカー | `submission_pipeline._handle_rejected()`（上限超過） |
| `task_completed` | 依頼者 | 合格人数が充足したとき / 期限切れ時に合格が1件以上あるとき |
| `task_expired` | 依頼者 | `expire_tasks.expire_overdue_tasks()` |

一覧は最新50件まで返す（`notification_repo.list_for_user(limit=50)`）。

---

### 2.9 task_likes （`app/models/task_like.py`）

投稿（依頼）への「いいね」。1ユーザー×1依頼につき1行。取り消したら行を削除する（履歴は残さない）。

| カラム | 型 | 制約 | 説明 |
|---|---|---|---|
| id | uuid | PK | |
| user_id | uuid | FK→users.id ON DELETE CASCADE, NOT NULL | |
| task_id | uuid | FK→tasks.id ON DELETE CASCADE, NOT NULL | |
| created_at | timestamptz | NOT NULL DEFAULT now() | いいね欄の並び順に使う |

```sql
ALTER TABLE task_likes ADD CONSTRAINT uq_task_like_user_task UNIQUE (user_id, task_id);
CREATE INDEX idx_task_likes_user ON task_likes (user_id, created_at DESC);
```

- 件数は `tasks.like_count` に持たせる（一覧のN+1を避けるための非正規化）。
- **自分が出した依頼にはいいねできない**（受注できない依頼をいいね欄に溜めないため）。

---

### 2.10 saved_searches （`app/models/saved_search.py`）

いいね欄に並べる「保存した検索条件」。1ユーザー**20件**まで（`MAX_SAVED_SEARCHES`。アプリ側で制限）。

| カラム | 型 | 制約 | 説明 |
|---|---|---|---|
| id | uuid | PK | |
| user_id | uuid | FK→users.id ON DELETE CASCADE, NOT NULL | |
| label | text | NOT NULL | 表示名。未指定時は「〈住所〉 から5km」を自動生成 |
| center_lat / center_lng | double precision | NOT NULL | 検索の中心 |
| location_address | text | | 検索に使った住所（表示用） |
| radius_km | double precision | NOT NULL DEFAULT 5 | |
| sort | text | NOT NULL DEFAULT 'distance' | distance / reward / deadline |
| last_match_count | int | | 該当件数。**一覧を開くたびに再計算して更新する** |
| created_at | timestamptz | NOT NULL DEFAULT now() | |

```sql
CREATE INDEX idx_saved_searches_user ON saved_searches (user_id, created_at DESC);
```

---

### 2.11 worker_reviews （`app/models/worker_review.py`）

依頼者によるワーカー評価。**合格済みの提出1件につき1回だけ**。

| カラム | 型 | 制約 | 説明 |
|---|---|---|---|
| id | uuid | PK | |
| submission_id | uuid | FK→submissions.id ON DELETE CASCADE, NOT NULL, INDEX | |
| task_id | uuid | FK→tasks.id ON DELETE CASCADE, NOT NULL, INDEX | |
| reviewer_id | uuid | FK→users.id ON DELETE CASCADE, NOT NULL, INDEX | 依頼者 |
| worker_id | uuid | FK→users.id ON DELETE CASCADE, NOT NULL, INDEX | 評価されるワーカー |
| rating | int | NOT NULL, CHECK BETWEEN 1 AND 5 | |
| tags | jsonb | NOT NULL DEFAULT '[]' | `as_requested` / `clear_photo` / `fast_response` / `accurate_location` |
| comment | varchar(500) | | 任意 |
| created_at | timestamptz | NOT NULL DEFAULT now() | |

```sql
ALTER TABLE worker_reviews ADD CONSTRAINT uq_worker_reviews_submission UNIQUE (submission_id);
```

- 評価できるのは**依頼者本人**、かつ提出が `approved` のときだけ。二重評価は `409 REVIEW_ALREADY_EXISTS`。
- **ワーカー本人には評価者を伏せて返す**（`ReceivedWorkerReview` に `reviewer_id` を含めない）。
- 平均評価は `tasks.min_worker_rating` による受注の足切りにも使う。
  ただし**評価が1件も無いワーカーは足切りしない**（新規が永久に受注できなくなるため）。
- `trust_score`（0〜100・自動計算）とは**別の指標**。評価は人が付ける1〜5の星。

---

## 3. ステータス遷移

### 3.1 tasks

```
[作成] → screening
   ├─ content_filter が該当 / AI審査で safety・risk が fail → rejected   （終端。画面②で赤表示）
   ├─ validity が fail、または score < 閾値                  → needs_info （画面②で補足要求 → resubmit で screening へ戻る）
   └─ 合格                                                   → open       （掲示板に公開）

open
   ├─ 1人目が受注                 → in_progress
   ├─ deadline_at 超過            → expired      （掲示板から外れる）
   └─ クライアントが取消          → cancelled

in_progress
   ├─ approved_worker_count が required_worker_count に到達 → completed
   ├─ 有効な受注が0件になり、かつ期限内                     → open（再開放）
   │     ※ 失格（failed）・辞退（withdraw）の両方で起きる
   └─ deadline_at 超過                                      → expired
        ※ expired時点で approved が1件以上あれば completed として扱う
```

`open` / `in_progress` の間は、依頼者が `deadline_at` を**後ろへだけ**延長できる
（`POST /api/tasks/{id}/extend-deadline`）。期限を過ぎた依頼は延長できない。

### 3.2 task_assignments

```
accepted
  ├─ 画像提出                    → submitted
  ├─ ワーカーが辞退（未提出時のみ）→ cancelled  （枠を再開放。受け直しは可能）
  └─ 期限超過                    → expired

submitted
  ├─ 検品合格                                → approved（終端。報酬確定 D-07）
  ├─ 不合格 かつ retake_count < MAX_RETAKE_COUNT → accepted（retake_count += 1、再撮影指示）
  ├─ 不合格 かつ retake_count = MAX_RETAKE_COUNT → failed  （終端。枠を再開放 D-08）
  └─ 検品エラー（error）                      → accepted（retake_count は増やさない）
```

**一度でも提出したら辞退できない**（`withdraw` は `accepted` かつ提出0件のときだけ）。

### 3.3 submissions

```
pending → processing → approved / rejected / error
```

`error`（AI呼び出し失敗など）は**ワーカーの責任ではない**ため、`retake_count` を増やさずに再提出を許可する。

### 3.4 削除について

**物理削除は行わない。** 掲示板からの「削除」は `status` による絞り込みで表現する
（監査ログと合格済み取引を保全するため）。

---

## 4. シードデータ

### 4.1 デモユーザー `scripts/seed_demo_users.py`

固定UUIDを使うため、何度実行しても同じユーザーになる（既存なら値を更新する）。

| login_id | display_name | trust_score | UUID |
|---|---|---|---|
| demo_company | デモ株式会社 | 50.0 | `11111111-…-111111111111` |
| yamada | 山田 太郎 | 92.0 | `22222222-…-222222222222` |
| sato | 佐藤 花子 | 78.0 | `33333333-…-333333333333` |
| suzuki | 鈴木 一郎 | 55.0 | `44444444-…-444444444444` |

パスワードは全アカウント共通で `spotcheck123`（`DEMO_USER_PASSWORD` で上書き可）。
ロールは無いので、どのアカウントでも依頼の作成と受注の両方ができる。

### 4.2 デモ依頼 `scripts/seed_demo_tasks.py`

一覧・いいね欄・タグ（SOLD / HOT / NEW）の見え方を確認するための投稿。
依頼主は `demo_company`。**AI審査は通さず `open` の状態で直接投入する**（画面確認が目的のため）。
投入後にサムネイルを生成する（外部APIが未設定ならプレースホルダになる）。

### 4.3 その他

| スクリプト | 内容 |
|---|---|
| `scripts/seed_worker_review_demo.py` | ワーカー評価の表示確認用データ |
| `scripts/init_storage.py` | Storage のバケット2つを作成する |
| `scripts/regenerate_thumbnails.py` | サムネイルの意匠を変えたときに `--force` で作り直す |
| `scripts/download_yolo_models.py` | `models_weights/` へ YOLO の重みを取得する |
