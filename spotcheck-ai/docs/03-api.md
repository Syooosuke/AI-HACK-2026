# 03. API仕様

ベースURL: `http://localhost:8000`
すべてのレスポンスは `application/json`（画像アップロードのみ `multipart/form-data` で受ける）。

---

## 1. 共通仕様

### 1.1 認証（デモ用 / D-06）

すべてのリクエストにヘッダーを付与する。

```
X-Demo-User-Id: <users.id の UUID>
```

- ヘッダーが無い、または存在しないIDの場合は `401 UNAUTHENTICATED` を返す。
- 各エンドポイントは、要求ロール（client / worker）と一致しない場合 `403 FORBIDDEN` を返す。
- `app/api/deps.py` に `get_current_user()` / `require_role(role)` を実装し、本認証への差し替え時にここだけ修正すれば済む構造にする。

### 1.2 エラーレスポンス

HTTPステータスに関わらず、エラーは以下の形式で統一する。

```json
{
  "error": {
    "code": "TASK_NOT_FOUND",
    "message": "指定された依頼が見つかりません。",
    "details": {}
  }
}
```

| HTTP | code の例 | 用途 |
|---|---|---|
| 400 | `VALIDATION_ERROR` | 入力値不正。`details` にフィールド別エラー |
| 401 | `UNAUTHENTICATED` | ヘッダー欠落 |
| 403 | `FORBIDDEN` | ロール不一致・他人のリソース |
| 404 | `TASK_NOT_FOUND` `SUBMISSION_NOT_FOUND` | |
| 409 | `TASK_FULL` `ALREADY_ACCEPTED` `INVALID_STATE` `RETAKE_LIMIT_EXCEEDED` | 状態競合 |
| 413 | `FILE_TOO_LARGE` | 画像サイズ超過 |
| 502 | `AI_SERVICE_ERROR` | OrcaRouter呼び出し失敗 |

### 1.3 命名規則

- リクエスト/レスポンスのJSONキーは **camelCase**（フロントのTypeScriptに合わせる）。
- Pydanticモデルで `alias_generator` を使い、Python側は snake_case を維持する。

### 1.4 画像URL

- レスポンスに含める画像URLは **Supabase Storage の署名付きURL（有効期限1時間）** とする。
- `raw_image_url`（原本）は**いかなるレスポンスにも含めない**。ワーカー本人にも返さない。

---

## 2. エンドポイント一覧

| メソッド | パス | ロール | 概要 |
|---|---|---|---|
| GET | `/api/health` | - | ヘルスチェック |
| GET | `/api/users/demo` | - | デモユーザー一覧（画面切替用） |
| POST | `/api/tasks` | client | 依頼作成＋AI審査（同期） |
| POST | `/api/tasks/{taskId}/resubmit` | client | 補足情報を追記して再審査 |
| GET | `/api/tasks` | client | 自分の依頼一覧 |
| GET | `/api/tasks/{taskId}` | both | 依頼詳細＋進行状況 |
| GET | `/api/tasks/nearby` | worker | 近傍の公開依頼一覧 |
| POST | `/api/tasks/{taskId}/accept` | worker | 受注 |
| POST | `/api/tasks/{taskId}/cancel` | client | 依頼取消 |
| GET | `/api/assignments/mine` | worker | 自分の受注一覧 |
| POST | `/api/submissions` | worker | 画像＋メタデータ提出 |
| GET | `/api/submissions/{submissionId}` | both | 検品状況・結果のポーリング |
| GET | `/api/tasks/{taskId}/results` | client | 合格済み提出の一覧（画面⑨） |

---

## 3. 詳細

### 3.1 `POST /api/tasks` — 依頼作成＋AI審査

画面①→②に対応。**審査は同期実行**し、その結果をそのまま返す（画面②で即座に結果を出すため）。

**リクエスト**: `multipart/form-data`

| フィールド | 型 | 必須 | 制約 |
|---|---|---|---|
| `title` | string | ✓ | 1〜60文字 |
| `description` | string | ✓ | 10〜1000文字 |
| `locationLat` | number | ✓ | -90〜90 |
| `locationLng` | number | ✓ | -180〜180 |
| `locationAddress` | string | | 任意 |
| `scheduledAt` | string(ISO8601) | ✓ | 現在時刻より後 |
| `deadlineAt` | string(ISO8601) | ✓ | `scheduledAt` 以降 |
| `rewardAmount` | int | ✓ | 100〜100000 |
| `requiredWorkerCount` | int | ✓ | 1〜10 |
| `referenceImages` | file[] | | 最大3枚、各15MBまで |

**処理フロー**
1. 入力バリデーション → 失敗なら `400`。
2. tasks を `status='screening'` で作成、参考画像をStorageへ保存。
3. `task_review` サービスを同期呼び出し（`docs/04-ai-pipeline.md` 参照）。
4. 判定に応じて status を更新。
5. 結果を返す。

**レスポンス `201 Created`**

```json
{
  "task": {
    "id": "uuid",
    "status": "open",
    "title": "駅前の再開発工事の調査",
    "reviewScore": 85,
    "reviewSummary": "駅前の再開発工事の進捗状況と安全対策の様子を確認したい。",
    "deadlineAt": "2026-05-28T14:00:00+09:00",
    "rewardAmount": 2000,
    "requiredWorkerCount": 1
  },
  "review": {
    "decision": "approved",
    "score": 85,
    "checks": {
      "safety": "pass",
      "validity": "pass",
      "risk": "pass",
      "duplication": "pass"
    },
    "missingInfo": [],
    "rejectionReason": null
  }
}
```

`decision` は3値: `approved`（→`open`） / `needs_info`（→`needs_info`） / `rejected`（→`rejected`）。
`needs_info` の場合 `missingInfo` に不足項目の文字列配列を入れ、画面②で補足要求として表示する。

---

### 3.2 `POST /api/tasks/{taskId}/resubmit` — 補足して再審査

`status='needs_info'` のときのみ許可（それ以外は `409 INVALID_STATE`）。

**リクエスト**
```json
{ "description": "更新後の詳細メッセージ全文", "scheduledAt": "...", "rewardAmount": 3000 }
```
`description` は必須、他は任意（差分更新）。

**処理**: 値を更新 → `status='screening'` → 再度AI審査 → 結果を返す（レスポンス形式は 3.1 と同じ）。
再審査の回数上限は設けない。

---

### 3.3 `GET /api/tasks/nearby` — 近傍タスク検索

画面④に対応。

**クエリパラメータ**

| 名前 | 型 | 既定値 | 説明 |
|---|---|---|---|
| `lat` | number | 必須 | ワーカーの現在地 |
| `lng` | number | 必須 | |
| `radiusKm` | number | 5 | 0.5〜50 |
| `limit` | int | 50 | 最大100 |
| `sort` | string | `distance` | `distance` / `reward` / `deadline` |

**抽出条件**
- `status = 'open'` または（`status='in_progress'` かつ 空き枠あり）
- `deadline_at > now()`
- バウンディングボックスで粗く絞り、Haversineで正確な距離を計算して `radiusKm` 内に限定

**レスポンス `200`**
```json
{
  "tasks": [
    {
      "id": "uuid",
      "title": "駅前の再開発工事の調査",
      "rewardAmount": 2000,
      "distanceKm": 1.2,
      "scheduledAt": "2026-05-28T14:00:00+09:00",
      "deadlineAt": "2026-05-28T14:00:00+09:00",
      "locationLat": 35.6595,
      "locationLng": 139.7005,
      "remainingSlots": 1,
      "requiredWorkerCount": 1
    }
  ]
}
```

`remainingSlots = required_worker_count − COUNT(status IN ('accepted','submitted','approved'))`

---

### 3.4 `GET /api/tasks/{taskId}` — 依頼詳細

ロールによって返す内容を変える。

**共通部分**: id, title, description, location*, scheduledAt, deadlineAt, rewardAmount, requiredWorkerCount, status, referenceImages[]

**client のとき追加**: `timeline`（画面③の進行状況タイムライン）
```json
"timeline": [
  { "step": "published",   "label": "依頼公開",   "status": "done",    "at": "2026-05-24T10:30:00+09:00" },
  { "step": "accepted",    "label": "ワーカーが受注", "status": "done",    "at": "..." },
  { "step": "in_survey",   "label": "現地調査中",  "status": "current", "at": null },
  { "step": "submitted",   "label": "結果提出",   "status": "pending", "at": null },
  { "step": "completed",   "label": "完了",      "status": "pending", "at": null }
]
```
`status` は `done` / `current` / `pending` の3値。

**worker のとき追加**: `distanceKm`（クエリ `lat`/`lng` があれば計算）、`myAssignment`（自分の受注状況。無ければ null）

> **ワーカーには他ワーカーの提出画像を返さない。**

---

### 3.5 `POST /api/tasks/{taskId}/accept` — 受注

画面⑤に対応。リクエストボディなし。

**処理（1トランザクション）**
1. `SELECT ... FOR UPDATE` で tasks をロック。
2. `deadline_at` 超過 → `409 INVALID_STATE`。
3. 同一ワーカーの有効な assignment が既にある → `409 ALREADY_ACCEPTED`。
4. 空き枠なし → `409 TASK_FULL`。
5. assignment を `accepted` で作成。tasks を `in_progress` に更新。

**レスポンス `201`**
```json
{
  "assignment": { "id": "uuid", "taskId": "uuid", "status": "accepted", "retakeCount": 0, "remainingRetakes": 2 }
}
```

---

### 3.6 `POST /api/submissions` — 画像提出（D-02）

画面⑥に対応。**最重要エンドポイント。**

**リクエスト**: `multipart/form-data`

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `assignmentId` | string(uuid) | ✓ | |
| `image` | file | ✓ | jpeg/png/webp、15MBまで |
| `capturedLat` | number | ✓ | 撮影瞬間の Geolocation 緯度 |
| `capturedLng` | number | ✓ | 同 経度 |
| `capturedAccuracyM` | number | | `coords.accuracy` |
| `capturedAt` | string(ISO8601) | ✓ | 端末側の撮影時刻 |
| `deviceInfo` | string(JSON) | | userAgent、プラットフォーム、画面サイズ |

**バリデーション（同期・API内）**
1. assignment が存在し、リクエスト元が所有者か → 否なら `403`。
2. assignment.status が `accepted` か → 否なら `409 INVALID_STATE`。
3. `retake_count > MAX_RETAKE_COUNT` → `409 RETAKE_LIMIT_EXCEEDED`。
4. `capturedAt` とサーバー時刻の差が `CAPTURE_FRESHNESS_SECONDS` 超 → `400`（撮り置き画像の投稿を防ぐ）。
5. ファイル形式・サイズ検証。

**処理**
1. 原本を `STORAGE_BUCKET_RAW` に保存。
2. EXIF抽出（失敗しても続行）。
3. submissions を `attempt_no = retake_count + 1`、`ai_validation_status='pending'` で作成。
4. assignment を `submitted` に更新。
5. **`BackgroundTasks` に検品パイプラインを登録**し、即座にレスポンスを返す。

**レスポンス `202 Accepted`**
```json
{
  "submission": { "id": "uuid", "attemptNo": 1, "aiValidationStatus": "pending" },
  "pollUrl": "/api/submissions/{id}"
}
```

---

### 3.7 `GET /api/submissions/{submissionId}` — 検品結果のポーリング

画面⑦⑧に対応。フロントは2秒間隔でポーリングし、`aiValidationStatus` が `pending`/`processing` 以外になったら停止する。

**レスポンス `200`**
```json
{
  "id": "uuid",
  "attemptNo": 1,
  "aiValidationStatus": "rejected",
  "aiScore": 48,
  "realityScore": 92,
  "processedImageUrl": null,
  "checks": {
    "framing_ok": true,
    "subject_present": true,
    "location_verified": true,
    "privacy_masked": false
  },
  "issues": [
    { "code": "TOO_DARK", "message": "暗すぎます" },
    { "code": "ANGLE_MISMATCH", "message": "別アングルで再撮影してください" }
  ],
  "retake": { "allowed": true, "remaining": 1 },
  "assignmentStatus": "accepted"
}
```

- `approved` のとき: `processedImageUrl` にマスキング済み画像の署名URL、`issues` は空、`retake.allowed` は false。
- `rejected` かつ再撮影上限到達のとき: `retake.allowed = false`、`assignmentStatus = "failed"`。
- `error` のとき: `retake` はカウントされず再提出可能。`issues` に `OTHER` を1件入れる。

**画面⑦のチェック項目とのマッピング**

| 画面表示 | レスポンスのキー |
|---|---|
| 構図確認 | `checks.framing_ok` |
| 対象物確認 | `checks.subject_present` |
| 位置・時刻確認 | `checks.location_verified` |
| 顔 / ナンバー保護 | `checks.privacy_masked` |

---

### 3.8 `GET /api/tasks/{taskId}/results` — 結果閲覧（画面⑨⑩）

client のみ。`ai_validation_status='approved'` の submission のみを返す（D-07により、全員の完了を待たず随時追加される）。

**レスポンス `200`**
```json
{
  "taskId": "uuid",
  "status": "completed",
  "resultSummary": "工事は予定通り進行中。安全対策は適切に実施されています。",
  "approvedCount": 1,
  "requiredWorkerCount": 1,
  "results": [
    {
      "submissionId": "uuid",
      "processedImageUrl": "https://.../signed",
      "capturedAt": "2026-05-28T13:42:00+09:00",
      "capturedLat": 35.6595,
      "capturedLng": 139.7005,
      "locationLabel": "渋谷区○○ 1-1-1付近",
      "realityScore": 92,
      "aiSummary": "工事は予定通り進行中。安全対策は適切に実施されています。",
      "worker": { "displayName": "山田 太郎", "trustScore": 4.8, "avatarUrl": null }
    }
  ]
}
```

`worker.trustScore` は表示用に5段階へ換算する（`trust_score / 20`、小数第1位まで）。

---

### 3.9 `POST /api/tasks/{taskId}/cancel`

`status` が `screening` / `needs_info` / `open` のときのみ許可。
`in_progress`（受注済み）の場合は `409 INVALID_STATE` とし、**受注済みワーカーが不利益を被らないようにする。**

---

## 4. バックグラウンドジョブ

### 4.1 期限超過タスクのクローズ

`app/jobs/expire_tasks.py` を **APScheduler** で5分ごとに実行する。

**処理**
1. `deadline_at < now()` かつ `status IN ('open','in_progress','needs_info','screening')` を抽出。
2. `approved_worker_count > 0` なら `completed`、そうでなければ `expired` に更新。
3. 未完了の assignment（`accepted` / `submitted`）を `expired` に更新。

> **物理削除は行わない。** 掲示板からの「削除」は `status` による絞り込みで表現する（監査ログと合格済み取引を保全するため）。

### 4.2 起動時の実行

FastAPIの `lifespan` でスケジューラを起動・停止する。起動直後にも1回実行し、停止中に期限切れになったタスクを回収する。