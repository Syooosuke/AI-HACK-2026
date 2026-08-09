# 02. データベース設計

DB: PostgreSQL (Supabase)。マイグレーションは Alembic で管理する。
すべての主キーは `uuid`（`gen_random_uuid()`）、時刻は `timestamptz`（UTC保存）とする。

---

## 1. ENUM定義

```sql
CREATE TYPE user_role          AS ENUM ('client', 'worker');
CREATE TYPE task_status        AS ENUM ('screening', 'rejected', 'needs_info', 'open', 'in_progress', 'completed', 'expired', 'cancelled');
CREATE TYPE assignment_status  AS ENUM ('accepted', 'submitted', 'approved', 'failed', 'cancelled', 'expired');
CREATE TYPE validation_status  AS ENUM ('pending', 'processing', 'approved', 'rejected', 'error');
CREATE TYPE payment_direction  AS ENUM ('charge', 'payout');
CREATE TYPE payment_status     AS ENUM ('stub_pending', 'stub_succeeded', 'stub_failed');
```

---

## 2. テーブル定義

### 2.1 users

デモ用の固定ユーザーをシードして使う（D-06）。1ユーザーは1ロールを持つ。

| カラム | 型 | 制約 | 説明 |
|---|---|---|---|
| id | uuid | PK | |
| role | user_role | NOT NULL | client / worker |
| display_name | text | NOT NULL | 表示名 |
| email | text | UNIQUE | デモ用のダミーで可 |
| trust_score | numeric(4,1) | NOT NULL DEFAULT 50.0 | 0〜100。ワーカーの信頼度 |
| completed_task_count | int | NOT NULL DEFAULT 0 | 承認された提出の累計 |
| avatar_url | text | | |
| created_at | timestamptz | NOT NULL DEFAULT now() | |

**trust_score の更新ルール**
- 検品合格（`approved`）: +2.0
- 再撮影上限超過による失格（`failed`）: −5.0
- 上下限は 0〜100 でクリップする。

---

### 2.2 tasks

| カラム | 型 | 制約 | 説明 |
|---|---|---|---|
| id | uuid | PK | |
| client_id | uuid | FK→users.id, NOT NULL | |
| title | text | NOT NULL | 依頼タイトル |
| description | text | NOT NULL | 詳細メッセージ（撮影条件） |
| location_lat | double precision | NOT NULL | 依頼地点の緯度 |
| location_lng | double precision | NOT NULL | 依頼地点の経度 |
| location_address | text | | 逆ジオコーディング結果 |
| scheduled_at | timestamptz | NOT NULL | 撮影してほしい日時 |
| deadline_at | timestamptz | NOT NULL | この時刻を過ぎたら掲示板から削除（`expired`） |
| reward_amount | int | NOT NULL, CHECK > 0 | 1人あたりの報酬（円） |
| required_worker_count | int | NOT NULL DEFAULT 1, CHECK BETWEEN 1 AND 10 | 撮影人数（D-05） |
| approved_worker_count | int | NOT NULL DEFAULT 0 | 検品合格済み人数 |
| status | task_status | NOT NULL DEFAULT 'screening' | |
| review_score | int | | AI審査の十分性スコア 0〜100 |
| review_summary | text | | AI生成の依頼要約（画面③に表示） |
| review_feedback | jsonb | | 不足情報のリスト・却下理由 |
| result_summary | text | | 全提出を踏まえたAI要約（画面⑩に表示） |
| created_at | timestamptz | NOT NULL DEFAULT now() | |
| updated_at | timestamptz | NOT NULL DEFAULT now() | |

**インデックス**
```sql
CREATE INDEX idx_tasks_status_deadline ON tasks (status, deadline_at);
CREATE INDEX idx_tasks_location        ON tasks (location_lat, location_lng);
CREATE INDEX idx_tasks_client          ON tasks (client_id, created_at DESC);
```

> 近傍検索は初期実装ではバウンディングボックス＋Haversine計算で行う。PostGISは導入しない。

---

### 2.3 task_reference_images

クライアントが「期待する画像イメージ」としてアップロードする参考画像。

| カラム | 型 | 制約 | 説明 |
|---|---|---|---|
| id | uuid | PK | |
| task_id | uuid | FK→tasks.id ON DELETE CASCADE | |
| image_url | text | NOT NULL | Storageのパス |
| sort_order | int | NOT NULL DEFAULT 0 | |
| created_at | timestamptz | NOT NULL DEFAULT now() | |

上限は1依頼あたり3枚とする。

---

### 2.4 task_assignments

ワーカーの受注枠。1依頼につき最大 `required_worker_count` 件まで `accepted` 状態を持てる。

| カラム | 型 | 制約 | 説明 |
|---|---|---|---|
| id | uuid | PK | |
| task_id | uuid | FK→tasks.id, NOT NULL | |
| worker_id | uuid | FK→users.id, NOT NULL | |
| status | assignment_status | NOT NULL DEFAULT 'accepted' | |
| retake_count | int | NOT NULL DEFAULT 0 | 再撮影を指示した回数（0〜2） |
| accepted_at | timestamptz | NOT NULL DEFAULT now() | |
| completed_at | timestamptz | | approved または failed になった時刻 |

**制約**
```sql
ALTER TABLE task_assignments ADD CONSTRAINT uq_assignment_task_worker UNIQUE (task_id, worker_id);
```

**受注時の同時実行制御（必須）**

受注枠の超過を防ぐため、`POST /api/tasks/{id}/accept` では以下をひとつのトランザクションで行う。

```sql
SELECT ... FROM tasks WHERE id = :task_id FOR UPDATE;
-- 有効枠 = required_worker_count
-- 使用中 = COUNT(assignments WHERE status IN ('accepted','submitted','approved'))
-- 使用中 >= 有効枠 なら 409 Conflict を返す
```

`failed` / `cancelled` / `expired` の枠はカウントに含めないため、自動的に他ワーカーへ再開放される（D-08）。

---

### 2.5 submissions

ワーカーの提出物。1つの assignment に対して最大3件（初回＋再撮影2回）作られる。

| カラム | 型 | 制約 | 説明 |
|---|---|---|---|
| id | uuid | PK | |
| assignment_id | uuid | FK→task_assignments.id, NOT NULL | |
| task_id | uuid | FK→tasks.id, NOT NULL | 検索用の非正規化 |
| worker_id | uuid | FK→users.id, NOT NULL | 同上 |
| attempt_no | int | NOT NULL | 1〜3 |
| raw_image_url | text | NOT NULL | **原本。クライアントには絶対に返さない** |
| processed_image_url | text | | マスキング済み画像 |
| captured_lat | double precision | NOT NULL | 撮影時のデバイス位置（D-02） |
| captured_lng | double precision | NOT NULL | 同上 |
| captured_accuracy_m | double precision | | Geolocation APIの精度 |
| captured_at | timestamptz | NOT NULL | 端末側の撮影時刻（D-02） |
| received_at | timestamptz | NOT NULL DEFAULT now() | サーバー受信時刻 |
| device_info | jsonb | | userAgent, プラットフォーム, 画面サイズ |
| exif_data | jsonb | | 抽出できたEXIF（補助検証用） |
| ai_validation_status | validation_status | NOT NULL DEFAULT 'pending' | |
| ai_score | int | | 検品スコア 0〜100 |
| ai_feedback | jsonb | | 再撮影指示の配列。画面⑧に表示 |
| location_check | jsonb | | 位置整合チェックの結果（下記構造） |
| masking_result | jsonb | | 検出・ぼかしを適用した領域の情報 |
| reality_score | int | | 信頼度スコア 0〜100（画面⑨⑩に表示） |
| created_at | timestamptz | NOT NULL DEFAULT now() | |

**制約**
```sql
ALTER TABLE submissions ADD CONSTRAINT uq_submission_attempt UNIQUE (assignment_id, attempt_no);
ALTER TABLE submissions ADD CONSTRAINT ck_attempt_no CHECK (attempt_no BETWEEN 1 AND 3);
CREATE INDEX idx_submissions_task ON submissions (task_id, created_at DESC);
```

**`location_check` の構造**
```json
{
  "distance_m": 42.5,
  "within_tolerance": true,
  "timestamp_delta_seconds": 63,
  "timestamp_consistent": true,
  "exif_gps_present": true,
  "exif_gps_conflict": false,
  "environment_consistency": {
    "expected_daylight": true,
    "observed_daylight": true,
    "note": "画像内の光の状態は撮影時刻と矛盾しない"
  },
  "flags": []
}
```

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
    { "code": "TOO_DARK", "message": "暗すぎます" },
    { "code": "ANGLE_MISMATCH", "message": "別アングルで再撮影してください" }
  ],
  "summary": "看板は写っていますが、露出が不足しています。"
}
```

`issues[].code` は画面⑧が固定文言を出せるよう、以下の定義済みコードのみを使う。
`SUBJECT_MISSING` / `TOO_DARK` / `TOO_BLURRY` / `ANGLE_MISMATCH` / `TOO_FAR` / `OBSTRUCTED` / `LOCATION_MISMATCH` / `TIMESTAMP_MISMATCH` / `OTHER`

---

### 2.6 payments（スタブ / D-03）

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

検品合格時に `charge` と `payout` を1件ずつ作成し、即座に `stub_succeeded` にする。
**外部決済SDKの導入・カード番号や口座番号の保存は行わない。**

---

### 2.7 ai_invocations

AI呼び出しの監査ログ。デバッグとデモでの説明に使う。

| カラム | 型 | 説明 |
|---|---|---|
| id | uuid | PK |
| purpose | text | `task_review` / `image_validation` / `environment_check` / `result_summary` |
| related_type | text | `task` / `submission` |
| related_id | uuid | 対象レコードのID |
| model | text | 実際に使われたモデル名（OrcaRouterの応答から取得） |
| request_payload | jsonb | 画像はURL参照に置換して保存する（base64は保存しない） |
| response_payload | jsonb | 生レスポンス |
| latency_ms | int | |
| is_stub | boolean | スタブモードでの応答か |
| error | text | |
| created_at | timestamptz | |

---

## 3. ステータス遷移

### 3.1 tasks

```
[作成] → screening
   ├─ 犯罪性・撮影禁止を検知      → rejected     （終端。画面②で赤表示）
   ├─ 十分性スコア < 閾値         → needs_info   （画面②で補足を要求。再提出で screening へ戻る）
   └─ 合格                        → open         （掲示板に公開）

open
   ├─ 1人目が受注                 → in_progress
   ├─ deadline_at 超過            → expired      （掲示板から削除）
   └─ クライアントが取消          → cancelled

in_progress
   ├─ approved_worker_count が required_worker_count に到達 → completed
   ├─ 全員が failed / cancelled で受注者0人 かつ 期限内     → open（再開放）
   └─ deadline_at 超過                                      → expired
        ※ expired時点で approved が1件以上あれば completed として扱う
```

### 3.2 task_assignments

```
accepted
  ├─ 画像提出                → submitted
  └─ ワーカーが辞退/期限超過 → cancelled / expired

submitted
  ├─ 検品スコア ≧ 閾値                    → approved（終端。報酬確定 D-07）
  ├─ 検品スコア < 閾値 かつ retake_count < 2 → accepted（retake_count += 1、再撮影指示）
  └─ 検品スコア < 閾値 かつ retake_count = 2 → failed  （終端。枠を再開放 D-08）
```

### 3.3 submissions

```
pending → processing → approved / rejected / error
```

`error`（AI呼び出し失敗など）は**ワーカーの責任ではない**ため、`retake_count` を増やさずに再提出を許可する。

---

## 4. シードデータ

`backend/scripts/seed_demo_users.py` で以下を作成する。

| role | display_name | 備考 |
|---|---|---|
| client | デモ株式会社 | 依頼作成に使用 |
| worker | 山田 太郎 | trust_score 92.0、画面⑩の評価表示に対応 |
| worker | 佐藤 花子 | trust_score 78.0 |
| worker | 鈴木 一郎 | trust_score 55.0 |

固定UUIDを使い、フロントエンドの `demoUser.ts` からも同じIDを参照できるようにする。