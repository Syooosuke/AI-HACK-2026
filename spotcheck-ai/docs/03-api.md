# 03. API仕様

ベースURL: `http://localhost:8000`
すべてのレスポンスは `application/json`（画像アップロードのみ `multipart/form-data` で受ける）。

---

## 1. 共通仕様

### 1.1 認証（ログインID＋パスワード / D-06）

`POST /api/auth/login`（または `/api/auth/signup`）で得たトークンを、
以降のすべてのリクエストに付与する。

```
Authorization: Bearer <アクセストークン(JWT)>
```

- ヘッダーが無い・形式不正・署名不正・期限切れ・利用者が存在しない場合はいずれも `401 UNAUTHENTICATED`。
- **ロールによる出し分けは行わない。** 1アカウントで「依頼する」「撮影する」の両方ができる。
  権限は「依頼のオーナーか、その依頼の受注者か」で判定し、該当しなければ `403 FORBIDDEN` を返す。
- トークンは JWT（HS256）。鍵は `JWT_SECRET`、有効期間は `JWT_EXPIRE_DAYS`（既定30日）。
- `app/api/deps.py` の `get_current_user()` が唯一の入口。

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
| 401 | `UNAUTHENTICATED` `INVALID_CREDENTIALS` | 未ログイン・トークン不正・認証情報の誤り |
| 403 | `FORBIDDEN` `CANNOT_ACCEPT_OWN_TASK` `CANNOT_LIKE_OWN_TASK` | 他人のリソース・自分の依頼の受注／いいね |
| 404 | `TASK_NOT_FOUND` `SUBMISSION_NOT_FOUND` | |
| 409 | `TASK_FULL` `ALREADY_ACCEPTED` `INVALID_STATE` `RETAKE_LIMIT_EXCEEDED` `LOGIN_ID_TAKEN` `SAVED_SEARCH_LIMIT` | 状態競合・上限超過 |
| 413 | `FILE_TOO_LARGE` | 画像サイズ超過 |
| 502 | `AI_SERVICE_ERROR` | OrcaRouter呼び出し失敗 |

### 1.3 命名規則

- リクエスト/レスポンスのJSONキーは **camelCase**（フロントのTypeScriptに合わせる）。
- Pydanticモデルで `alias_generator` を使い、Python側は snake_case を維持する。

### 1.4 画像URL

- レスポンスに含める画像URLは **Supabase Storage の署名付きURL（有効期限1時間）** とする。
- `raw_image_url`（原本）は**いかなるレスポンスにも含めない**。ワーカー本人にも返さない。
- 例外はプロフィールのアイコン画像だけで、期限のない配信URLを返す（3.0.1 参照）。

---

## 2. エンドポイント一覧

「認証」列の `-` は認証不要、`必須` はトークンが必要なことを示す。
アクセス範囲はロールではなくリソースの所有関係で決まる。

| メソッド | パス | 認証 | 概要 |
|---|---|---|---|
| GET | `/api/health` | - | ヘルスチェック |
| POST | `/api/auth/signup` | - | 新規登録（トークンを返す） |
| POST | `/api/auth/login` | - | ログイン |
| GET | `/api/auth/me` | 必須 | ログイン中ユーザーの取得・トークン検証 |
| POST | `/api/users/me/avatar` | 必須 | 自分のアイコン画像を差し替える |
| DELETE | `/api/users/me/avatar` | 必須 | 自分のアイコン画像を削除して既定へ戻す |
| GET | `/api/users/{userId}/avatar` | - | アイコン画像の配信（`<img>` から直接読む） |
| GET | `/api/users/{userId}/public` | 必須 | 公開プロフィール（閲覧用） |
| POST | `/api/tasks` | 必須 | 依頼作成＋AI審査（同期） |
| POST | `/api/tasks/{taskId}/resubmit` | 必須 | 補足情報を追記して再審査（オーナーのみ） |
| GET | `/api/tasks` | 必須 | 自分が出した依頼の一覧 |
| GET | `/api/tasks/{taskId}` | 必須 | 依頼詳細＋進行状況 |
| GET | `/api/tasks/nearby` | 必須 | 近傍の公開依頼一覧（自分の依頼は除く） |
| POST | `/api/tasks/{taskId}/accept` | 必須 | 受注（自分の依頼は不可） |
| POST | `/api/tasks/{taskId}/cancel` | 必須 | 依頼取消（オーナーのみ） |
| GET | `/api/assignments/mine` | 必須 | 自分の受注一覧 |
| POST | `/api/submissions` | 必須 | 画像＋メタデータ提出 |
| GET | `/api/submissions/{submissionId}` | 必須 | 検品状況・結果のポーリング（本人とオーナーのみ） |
| GET | `/api/tasks/{taskId}/results` | 必須 | 合格済み提出の一覧（画面⑨。オーナーのみ） |
| POST | `/api/tasks/{taskId}/like` | 必須 | いいねを付ける（自分の依頼は不可） |
| DELETE | `/api/tasks/{taskId}/like` | 必須 | いいねを取り消す |
| GET | `/api/likes` | 必須 | いいねした投稿の一覧（いいね欄の上半分） |
| GET | `/api/saved-searches` | 必須 | 保存した検索条件（いいね欄の下半分） |
| POST | `/api/saved-searches` | 必須 | 検索条件を保存する |
| DELETE | `/api/saved-searches/{searchId}` | 必須 | 検索条件を削除する |

---

## 3. 詳細

### 3.0 認証 `/api/auth/*`

#### `POST /api/auth/signup` — 新規登録

**リクエスト**

| フィールド | 型 | 必須 | 制約 |
|---|---|---|---|
| `loginId` | string | ✓ | 3〜32文字。半角英数字とアンダースコアのみ |
| `password` | string | ✓ | 8文字以上・72バイト以内（bcryptの上限） |
| `displayName` | string | ✓ | 1〜40文字 |

- ログインIDが既に使われている場合は `409 LOGIN_ID_TAKEN`。
- 登録に成功するとそのままログイン状態にできるよう、トークンを返す（`201`）。

#### `POST /api/auth/login` — ログイン

**リクエスト**: `loginId` / `password`

- ログインIDの大文字小文字は区別しない。
- IDが存在しない場合とパスワード誤りは**同じ応答**にする（`401 INVALID_CREDENTIALS`）。
  IDの存在を推測させないため、メッセージも区別しない。

**レスポンス `200`**（signup も同じ形）
```json
{
  "token": "<JWT>",
  "tokenType": "Bearer",
  "expiresIn": 2592000,
  "user": {
    "id": "uuid",
    "loginId": "yamada",
    "displayName": "山田 太郎",
    "trustScore": 92.0,
    "completedTaskCount": 3,
    "avatarUrl": null
  }
}
```

> `passwordHash` はいかなるレスポンスにも含めない。

#### `GET /api/auth/me` — ログイン中ユーザー

保持しているトークンの有効性確認と、ユーザー情報の最新化に使う。

**レスポンス `200`**: `{ "user": { ...上と同じ } }`

---

### 3.0.1 アイコン画像 `/api/users/*/avatar`

`avatarUrl` は**署名付きURLではなく** `/api/users/{userId}/avatar?v=<版>` を返す（1.4 の例外）。
ログイン情報はブラウザの localStorage に残るため、有効期限付きURLだと次回起動時に
画像だけ表示できなくなるからである。`v` は画像内容のハッシュで、
差し替え時にブラウザのキャッシュを外すために付ける。

#### `POST /api/users/me/avatar` — 差し替え

**リクエスト**: `multipart/form-data`

| フィールド | 型 | 必須 | 制約 |
|---|---|---|---|
| `image` | file | ✓ | `ALLOWED_IMAGE_TYPES` / `MAX_UPLOAD_SIZE_MB` は提出画像と共通 |

- 中央を正方形に切り抜いて 256px のJPEGへ変換し、**加工済みバケット**へ保存する。
- 差し替えると古い画像はストレージから削除する。
- **レスポンス `200`**: `{ "user": { ...`GET /api/auth/me` と同じ } }`

#### `DELETE /api/users/me/avatar` — 削除

既定表示（表示名の頭文字を描いた丸）へ戻す。レスポンスは上と同じ形で `avatarUrl` が `null`。

#### `GET /api/users/{userId}/avatar` — 配信（認証不要）

`<img>` から読むため Authorization ヘッダーを付けられず、他ユーザーのアイコンも表示するため
**認証不要**とする。返すのは本人がアップロードしたアイコンのみで、提出画像の原本は扱わない。
未設定・不在ユーザーはどちらも `404 NOT_FOUND`。

---

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
| `lat` | number | 必須 | 検索の中心（現在地、または地図で検索した地点） |
| `lng` | number | 必須 | |
| `radiusKm` | number | 5 | 0.5〜50 |
| `limit` | int | 50 | 最大100 |
| `sort` | string | `distance` | `distance` / `reward` / `deadline` |

**抽出条件**
- `status = 'open'` または（`status='in_progress'` かつ 空き枠あり）
- `deadline_at > now()`
- **自分が出した依頼は除外する**（受注できないため）
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
      "locationAddress": "東京都渋谷区道玄坂1丁目",
      "remainingSlots": 1,
      "requiredWorkerCount": 1,
      "status": "open",
      "createdAt": "2026-05-24T10:30:00+09:00",
      "thumbnailUrl": "https://.../task-thumbnail/....jpg",
      "thumbnailSource": "generated",
      "badges": ["new"],
      "likeCount": 3,
      "isLiked": false,
      "viewCount": 21,
      "isMine": false
    }
  ]
}
```

`remainingSlots = required_worker_count − COUNT(status IN ('accepted','submitted','approved'))`

**投稿カード用のフィールド**（`/api/likes` も同じ形で返す）

| フィールド | 説明 |
|---|---|
| `thumbnailUrl` | 正方形サムネイルの配信URL。生成前は `null` |
| `thumbnailSource` | `reference` / `generated` / `streetview` / `placeholder` |
| `badges` | 優先順位の高い順の配列。`sold`（取引終了）> `hot`（閲覧20以上）> `new`（24時間以内）。カードは先頭1つだけを表示する |
| `likeCount` `isLiked` | いいねの数と、自分が押しているか |
| `viewCount` | 詳細を開かれた回数（オーナー自身の閲覧は数えない） |
| `isMine` | 自分が出した依頼か。`true` のときハートは出さない |

---

### 3.4 `GET /api/tasks/{taskId}` — 依頼詳細

依頼のオーナー（`client_id` が自分）か、それ以外（撮影する側）かで返す内容を変える。

**共通部分**: id, title, description, location*, scheduledAt, deadlineAt, rewardAmount, requiredWorkerCount, status, referenceImages[], createdAt, owner, thumbnailUrl, badges, likeCount, isLiked, viewCount, isMine

`owner` は依頼主。`id` を使って公開プロフィール（3.4.1）へ遷移できる。
`publishedTaskCount` / `completionRate` は依頼者としての実績で、受注前に「どんな依頼者か」を
判断できるようにするために出す。**母数は公開された依頼のみ**で、却下・審査中は含めない。
自分の依頼を見た場合も同じ形で返す（出し分けはしない）。

```json
"owner": {
  "id": "uuid",
  "displayName": "デモ株式会社",
  "trustScore": 92.0,
  "completedTaskCount": 3,
  "avatarUrl": null,
  "publishedTaskCount": 12,
  "completionRate": 0.75
}
```

**オーナーのとき追加**: `timeline`（画面③の進行状況タイムライン）
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

**オーナー以外のとき追加**: `distanceKm`（クエリ `lat`/`lng` があれば計算）、`myAssignment`（自分の受注状況。無ければ null）

> **撮影する側には他ワーカーの提出画像を返さない。**

---

### 3.4.1 `GET /api/users/{userId}/public` — 公開プロフィール（閲覧用）

依頼詳細の依頼主行から遷移する閲覧専用ページ用。**ロールによる出し分けはなく、ログインしていれば誰でも参照できる**
（1アカウントが依頼者とワーカーの両面を持ちうる）。認証は必要。

**レスポンス `200`**

```json
{
  "id": "uuid",
  "displayName": "デモ株式会社",
  "avatarUrl": null,
  "joinedAt": "2026-08-01T00:00:00+09:00",
  "asRequester": {
    "publishedTaskCount": 12,
    "completedTaskCount": 9,
    "completionRate": 0.75
  },
  "asWorker": {
    "trustScore": 4.6,
    "approvedSubmissionCount": 8
  }
}
```

- `404 USER_NOT_FOUND`: 存在しないユーザー
- `asRequester.completionRate` は母数0のとき `null`
- `asWorker.trustScore` は 0〜100 のまま返す（画面はゲージで表示する）
- 実績が0の側も省略せず返す（表示側で空状態を出す）

**公開してはならない項目**（実装は `app/services/user_service.py` に集約する）

| 項目 | 理由 |
|---|---|
| `email` / `login_id` | 個人情報・認証情報 |
| 却下（`rejected`）・審査中（`screening`）・情報補足待ち（`needs_info`）の依頼 | 却下件数が見えると「危険な依頼を出した人」と特定でき名誉に関わる。未公開の下書き相当 |
| 平均報酬 | 依頼者にとって相場を見られる不利がある（値下げ圧力・相場の固定化） |
| 依頼の本文・位置情報 | 個別の依頼詳細で足りる。プロフィールで束ねると行動追跡に使える |

統計の母数は**一度でも公開された依頼**、すなわち
`status IN ('open','in_progress','completed','expired','cancelled')`。

---

### 3.5 `POST /api/tasks/{taskId}/accept` — 受注

画面⑤に対応。リクエストボディなし。

**処理（1トランザクション）**
1. `SELECT ... FOR UPDATE` で tasks をロック。
2. 自分が出した依頼 → `403 CANNOT_ACCEPT_OWN_TASK`。
3. `deadline_at` 超過 → `409 INVALID_STATE`。
4. 同一ワーカーの有効な assignment が既にある → `409 ALREADY_ACCEPTED`。
5. 空き枠なし → `409 TASK_FULL`。
6. assignment を `accepted` で作成。tasks を `in_progress` に更新。

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
      "worker": {
        "displayName": "山田 太郎",
        "trustScore": 96.0,
        "avatarUrl": "/api/users/<uuid>/avatar?v=1f2e3d4c5b6a7890"
      }
    }
  ]
}
```

`worker.trustScore` は **0〜100 のまま**返す。画面はゲージ（最大値100）で表示するため、
5段階への換算は行わない。`avatarUrl` は 3.0.1 の配信URL（未設定なら `null`）。

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

---

### 3.10 いいね `/api/tasks/{taskId}/like` `/api/likes`

投稿カード右上のハートに対応する。

- `POST` / `DELETE` はどちらも**冪等**。二重タップでも件数はずれない。
- 自分が出した依頼にはいいねできない → `403 CANNOT_LIKE_OWN_TASK`
  （受注できない依頼をハート欄に溜めないため）。
- `tasks.like_count` に集計値を持たせ、一覧で件数を引くためのN+1を避ける。

**レスポンス `200`**（付けた場合・取り消した場合ともに同じ形）
```json
{ "taskId": "uuid", "liked": true, "likeCount": 3 }
```

`GET /api/likes` は**いいねした順（新しい順）**で投稿カードを返す。
取引終了（`completed`）した依頼も一覧から消さず、`badges` に `sold` を付けて返す。

---

### 3.11 保存した検索条件 `/api/saved-searches`

**`POST` リクエスト**

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `label` | string | | 一覧に出す名前。未指定なら「<住所> から5km」を自動生成 |
| `centerLat` / `centerLng` | number | ✓ | 検索の中心 |
| `locationAddress` | string | | 検索に使った住所（表示用） |
| `radiusKm` | number | | 0.5〜50（既定5） |
| `sort` | string | | `distance` / `reward` / `deadline` |

- 1ユーザーあたり20件まで。超過は `409 SAVED_SEARCH_LIMIT`。
- `lastMatchCount` には**一覧を開いた時点の該当件数**を入れて返す（保存後に増減するため）。
- 他ユーザーの条件は取得も削除もできない（`403 FORBIDDEN`）。
