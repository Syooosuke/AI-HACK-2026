# 03. API仕様

ベースURL: `http://localhost:8000`（本番は `docs/07-deployment.md` 5.1）
すべてのレスポンスは `application/json`。画像アップロードのみ `multipart/form-data` で受け、
画像配信（`/api/files/*` `/api/users/*/avatar`）だけがバイナリを返す。

FastAPI の自動生成ドキュメントは `GET /docs`。**このファイルはそれと実装の意図を補うもの。**

---

## 1. 共通仕様

### 1.1 認証（ログインID＋パスワード / D-06）

`POST /api/auth/login`（または `/api/auth/signup`）で得たトークンを、以降のすべてのリクエストに付与する。

```
Authorization: Bearer <アクセストークン(JWT)>
```

- ヘッダーが無い・形式不正・署名不正・期限切れ・利用者が存在しない場合はいずれも `401 UNAUTHENTICATED`。
- **ロールによる出し分けは行わない。** 1アカウントで「依頼する」「撮影する」の両方ができる。
  権限は「依頼のオーナーか、その依頼の受注者か」で判定し、該当しなければ `403 FORBIDDEN` を返す。
- トークンは JWT（HS256）。鍵は `JWT_SECRET`、有効期間は `JWT_EXPIRE_DAYS`（既定30日）。
  ペイロードは `sub`（ユーザーID）/ `typ="access"` / `iat` / `exp`。
- `app/api/deps.py` の `get_current_user()` が唯一の入口。

### 1.2 エラーレスポンス

HTTPステータスに関わらず、エラーは以下の形式で統一する（`app/main.py` の4つの例外ハンドラ）。

```json
{
  "error": {
    "code": "TASK_NOT_FOUND",
    "message": "指定された依頼が見つかりません。",
    "details": {}
  }
}
```

| HTTP | code | 用途 |
|---|---|---|
| 400 | `VALIDATION_ERROR` | 入力値不正。`details.fields` にフィールド別エラー |
| 401 | `UNAUTHENTICATED` / `INVALID_CREDENTIALS` | 未ログイン・トークン不正・認証情報の誤り |
| 403 | `FORBIDDEN` / `CANNOT_ACCEPT_OWN_TASK` / `CANNOT_LIKE_OWN_TASK` / `RATING_REQUIREMENT_NOT_MET` | 他人のリソース・自分の依頼の受注／いいね・評価条件を満たさない受注 |
| 404 | `NOT_FOUND` / `TASK_NOT_FOUND` / `SUBMISSION_NOT_FOUND` / `ASSIGNMENT_NOT_FOUND` / `USER_NOT_FOUND` / `TASK_REVIEW_NOT_FOUND` / `NOTIFICATION_NOT_FOUND` / `SAVED_SEARCH_NOT_FOUND` | |
| 409 | `INVALID_STATE` / `TASK_FULL` / `ALREADY_ACCEPTED` / `RETAKE_LIMIT_EXCEEDED` / `LOGIN_ID_TAKEN` / `SAVED_SEARCH_LIMIT` / `REVIEW_ALREADY_EXISTS` | 状態競合・上限超過 |
| 413 | `FILE_TOO_LARGE` | 画像サイズ超過 |
| 500 | `STORAGE_ERROR` / `INTERNAL_ERROR` | |
| 502 | `AI_SERVICE_ERROR` | OrcaRouter呼び出しの最終失敗 |

フロント側の文言は `frontend/src/lib/api/errorMessages.ts` に集約する（通信断は `NETWORK_ERROR`）。

### 1.3 命名規則

- リクエスト/レスポンスのJSONキーは **camelCase**（フロントのTypeScriptに合わせる）。
- Pydantic の `CamelModel`（`alias_generator=to_camel`）で変換し、Python側は snake_case を維持する。
- **例外**: `submissions.location_check` は保存された jsonb をそのまま返すため、
  中身のキーは snake_case のまま（`distance_m` / `within_tolerance` など）。

### 1.4 画像URL

- レスポンスに含める画像URLは **Supabase Storage の署名付きURL（有効期限1時間）** とする。
- ローカルストレージ運用時は `/api/files/{bucket}/{key}` という相対URLを返す。
  フロントは `resolveApiUrl()` でバックエンドを指す絶対URLへ変換する。
- **`raw_image_url`（原本）はいかなるレスポンスにも含めない。ワーカー本人にも返さない。**
- 例外はプロフィールのアイコン画像だけで、期限のない配信URLを返す（3.0.1 参照）。

### 1.5 リトライの扱い（フロント側）

`lib/api/client.ts` は **GET / HEAD の通信例外だけ1回再試行する**（600ms後）。
POST / DELETE は再試行しない（二重受注・二重依頼という実害が出るため）。

---

## 2. エンドポイント一覧

「認証」列の `-` は認証不要、`必須` はトークンが必要。アクセス範囲はロールではなくリソースの所有関係で決まる。

### ヘルスチェック・ファイル配信

| メソッド | パス | 認証 | 概要 |
|---|---|---|---|
| GET | `/api/health` | - | 依存先の状態と設定不足の警告 |
| GET | `/api/health/db` | - | DBへの到達確認 |
| GET | `/api/files/{bucket}/{key}` | - | ローカルストレージの**加工済み画像のみ**配信 |

### 認証・ユーザー

| メソッド | パス | 認証 | 概要 |
|---|---|---|---|
| POST | `/api/auth/signup` | - | 新規登録（トークンを返す） |
| POST | `/api/auth/login` | - | ログイン |
| GET | `/api/auth/me` | 必須 | ログイン中ユーザーの取得・トークン検証 |
| POST | `/api/users/me/avatar` | 必須 | 自分のアイコン画像を差し替える |
| DELETE | `/api/users/me/avatar` | 必須 | 自分のアイコン画像を削除して既定へ戻す |
| GET | `/api/users/me/reviews` | 必須 | 自分がワーカーとして受け取った評価（匿名） |
| GET | `/api/users/{userId}/avatar` | - | アイコン画像の配信（`<img>` から直接読む） |
| GET | `/api/users/{userId}/public` | 必須 | 公開プロフィール（閲覧用） |

### 依頼

| メソッド | パス | 認証 | 概要 |
|---|---|---|---|
| POST | `/api/tasks/generate-description` | 必須 | 依頼タイトルから短い詳細メッセージをAI生成 |
| POST | `/api/tasks` | 必須 | 依頼作成＋AI審査（同期） |
| POST | `/api/tasks/{taskId}/duplicate` | 必須 | 過去の依頼を日時だけ変更して再投稿（オーナーのみ） |
| POST | `/api/tasks/{taskId}/resubmit` | 必須 | 補足情報を追記して再審査（オーナーのみ） |
| GET | `/api/tasks` | 必須 | 自分が出した依頼の一覧 |
| GET | `/api/tasks/nearby` | 必須 | 近傍の公開依頼一覧（自分の依頼は除く） |
| GET | `/api/tasks/{taskId}` | 必須 | 依頼詳細＋進行状況 |
| GET | `/api/tasks/{taskId}/review` | 必須 | 保存済みのAI審査結果（オーナーのみ） |
| POST | `/api/tasks/{taskId}/accept` | 必須 | 受注（自分の依頼は不可） |
| POST | `/api/tasks/{taskId}/withdraw` | 必須 | 撮影提出前の受注辞退・募集枠の再開放 |
| POST | `/api/tasks/{taskId}/extend-deadline` | 必須 | 公開中・進行中の依頼の提出期限を延長（オーナーのみ） |
| POST | `/api/tasks/{taskId}/cancel` | 必須 | 依頼取消（オーナーのみ） |
| GET | `/api/tasks/{taskId}/results` | 必須 | 合格済み提出の一覧（画面⑨。オーナーのみ） |
| GET | `/api/assignments/mine` | 必須 | 自分の受注一覧 |

### 提出・評価

| メソッド | パス | 認証 | 概要 |
|---|---|---|---|
| POST | `/api/submissions` | 必須 | 画像＋メタデータ提出（`202 Accepted`） |
| GET | `/api/submissions/{submissionId}` | 必須 | 検品状況・結果のポーリング（本人とオーナーのみ） |
| POST | `/api/submissions/{submissionId}/review` | 必須 | 合格提出のワーカー評価（依頼者のみ） |

### いいね・保存した検索条件

| メソッド | パス | 認証 | 概要 |
|---|---|---|---|
| POST | `/api/tasks/{taskId}/like` | 必須 | いいねを付ける（自分の依頼は不可） |
| DELETE | `/api/tasks/{taskId}/like` | 必須 | いいねを取り消す |
| GET | `/api/likes` | 必須 | いいねした投稿の一覧（いいね欄の上半分） |
| GET | `/api/saved-searches` | 必須 | 保存した検索条件（いいね欄の下半分） |
| POST | `/api/saved-searches` | 必須 | 検索条件を保存する |
| DELETE | `/api/saved-searches/{searchId}` | 必須 | 検索条件を削除する |

### お知らせ

| メソッド | パス | 認証 | 概要 |
|---|---|---|---|
| GET | `/api/notifications` | 必須 | 自分宛てのお知らせ（新しい順・最大50件） |
| GET | `/api/notifications/unread-count` | 必須 | 未読件数（タブのバッジ用） |
| POST | `/api/notifications/{notificationId}/read` | 必須 | 1件を既読にする（`204`） |
| POST | `/api/notifications/read-all` | 必須 | すべて既読にする（`204`） |

---

## 3. 詳細

### 3.0 認証 `/api/auth/*`

#### `POST /api/auth/signup` — 新規登録

| フィールド | 型 | 必須 | 制約 |
|---|---|---|---|
| `loginId` | string | ✓ | 3〜32文字。半角英数字とアンダースコアのみ |
| `password` | string | ✓ | 8文字以上・**72バイト以内**（bcryptの上限） |
| `displayName` | string | ✓ | 1〜40文字 |

- ログインIDが既に使われている場合は `409 LOGIN_ID_TAKEN`（一意制約違反も同じコードに揃える）。
- 登録に成功するとそのままログイン状態にできるよう、トークンを返す（`201`）。

#### `POST /api/auth/login` — ログイン

**リクエスト**: `loginId` / `password`

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
    "avatarUrl": "/api/users/<uuid>/avatar?v=1f2e3d4c5b6a7890"
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
画像だけ表示できなくなるからである。`v` は画像内容のハッシュ（先頭16文字）で、
差し替え時にブラウザのキャッシュを外すために付ける。

#### `POST /api/users/me/avatar` — 差し替え

**リクエスト**: `multipart/form-data` の `image`
（`ALLOWED_IMAGE_TYPES` / `MAX_UPLOAD_SIZE_MB` は提出画像と共通）

- **EXIF の回転情報を適用してから**中央を正方形に切り抜き、256px のJPEGへ変換して
  **加工済みバケット**へ保存する。
- 差し替えると古い画像はストレージから削除する（削除に失敗しても差し替えは成功扱い）。
- **レスポンス `200`**: `{ "user": { ...`GET /api/auth/me` と同じ } }`

#### `DELETE /api/users/me/avatar` — 削除

既定表示（表示名の頭文字を描いた丸）へ戻す。レスポンスは上と同じ形で `avatarUrl` が `null`。

#### `GET /api/users/{userId}/avatar` — 配信（認証不要）

`<img>` から読むため Authorization ヘッダーを付けられず、他ユーザーのアイコンも表示するため
**認証不要**とする。返すのは本人がアップロードしたアイコンのみで、提出画像の原本は扱わない。
未設定・不在ユーザーはどちらも `404 NOT_FOUND`。`Cache-Control: public, max-age=86400`。

---

### 3.0.2 `GET /api/files/{bucket}/{key}` — ローカル画像配信（認証不要）

`STORAGE_BACKEND=local` のときの署名URLの代替。
**`bucket` が `STORAGE_BUCKET_PROCESSED` でなければ `403 FORBIDDEN`** を返す。
URLを推測されても原本バケットは配信しない、という最後の防御線。

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
| `scheduledAt` | string(ISO8601) | ✓ | 現在時刻の**15分前**より後（「今から撮ってほしい」を通すための猶予） |
| `deadlineAt` | string(ISO8601) | ✓ | `scheduledAt` 以降 |
| `rewardAmount` | int | ✓ | 100〜100000 |
| `requiredWorkerCount` | int | ✓ | 1〜10 |
| `minWorkerRating` | float | | 1.0〜5.0。受注できるワーカーの最低平均評価。省略で条件なし |
| `referenceImages` | file[] | | 最大3枚、各15MBまで |

**処理フロー**
1. 入力バリデーション → 失敗なら `400`。
2. tasks を `status='screening'` で作成、参考画像を**加工済みバケット**へ保存。
3. `content_filter.screen()` → 該当したらAIを呼ばず `rejected` 確定。
4. `task_review.review_task()` を同期呼び出し（`docs/04-ai-pipeline.md` 2節）。合議があれば並行実行。
5. 判定に応じて status を更新し、依頼者へお知らせを作成する。
6. `open` になった場合のみ、`BackgroundTasks` でサムネイル生成を予約する。
7. 結果を返す。

**レスポンス `201 Created`**

```json
{
  "task": {
    "id": "uuid",
    "status": "open",
    "title": "駅前の再開発工事の調査",
    "description": "…",
    "locationLat": 35.6595,
    "locationLng": 139.7005,
    "locationAddress": "東京都渋谷区道玄坂1丁目",
    "reviewScore": 85,
    "reviewSummary": "駅前の再開発工事の進捗状況と安全対策の様子を確認したい。",
    "scheduledAt": "2026-05-28T12:00:00+09:00",
    "deadlineAt": "2026-05-28T14:00:00+09:00",
    "rewardAmount": 2000,
    "requiredWorkerCount": 1,
    "minWorkerRating": null
  },
  "review": {
    "decision": "approved",
    "score": 85,
    "checks": { "safety": "pass", "validity": "pass", "risk": "pass", "duplication": "pass" },
    "missingInfo": [],
    "rejectionReason": null
  }
}
```

`decision` は3値: `approved`（→`open`） / `needs_info`（→`needs_info`） / `rejected`（→`rejected`）。
`missingInfo` は `needs_info` のときのみ、`rejectionReason` は `rejected` のときのみ値が入る。

> **審査の所要時間は実測20〜90秒。** 画面①は「30秒〜1分ほど」と案内する。

---

### 3.1.1 `POST /api/tasks/generate-description` — 詳細メッセージのAI生成

画面①の「AIで詳細を作成」。**依頼はまだ作らない**（下書き段階の補助）。

**リクエスト**: `{ "title": "駅前の工事の進捗確認" }`（1〜60文字）
**レスポンス `200`**: `{ "description": "…60〜180文字の生成文…" }`

生成後もユーザーが自由に編集できる。監査ログには `related_type="task_draft"` として残る。

---

### 3.1.2 `POST /api/tasks/{taskId}/duplicate` — 過去の依頼を再投稿

本人の過去依頼をテンプレートとして、**撮影希望日時と提出期限だけを差し替える**。

**リクエスト**: `{ "scheduledAt": "...", "deadlineAt": "..." }`

- 場所・報酬・人数・タイトル・詳細・評価条件を引き継ぎ、**独立した新規依頼として再びAI審査を通す**。
- 参考画像は再アップロードせず、加工済みストレージ上の**同じ保存キーを共有する**。
- レスポンス形式は 3.1 と同じ（`201`）。

---

### 3.2 `POST /api/tasks/{taskId}/resubmit` — 補足して再審査

`status='needs_info'` のときのみ許可（それ以外は `409 INVALID_STATE`）。

**リクエスト**
```json
{ "description": "更新後の詳細メッセージ全文", "scheduledAt": "...", "deadlineAt": "...", "rewardAmount": 3000 }
```
`description` は必須、他は任意（差分更新）。

**処理**: 値を更新 → `status='screening'` → 再度AI審査 → 結果を返す（レスポンス形式は 3.1 と同じ）。
再審査の回数上限は設けない。日時の再検証では「現在より後」の制約を外す（既に決まった予定を維持できるようにするため）。

> **`rejected` からは再審査できない。** 却下された依頼の言い換えによる回避を促さないための仕様
> （`docs/04-ai-pipeline.md` 1.2 の「合議の非対称性」も参照）。

---

### 3.2.1 `GET /api/tasks/{taskId}/review` — 保存済み審査結果

お知らせ（`task_needs_info` / `task_rejected`）から画面②を開き直すために使う。
オーナー以外は `403`、審査結果が無ければ `404 TASK_REVIEW_NOT_FOUND`。
レスポンス形式は 3.1 と同じ（`tasks.review_feedback` から復元する）。

---

### 3.3 `GET /api/tasks/nearby` — 近傍タスク検索

ホーム `/home` と地図 `/search` の両方が使う。

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
- **残り枠0の依頼は除外する**
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
      "scheduledAt": "2026-05-28T12:00:00+09:00",
      "deadlineAt": "2026-05-28T14:00:00+09:00",
      "locationLat": 35.6595,
      "locationLng": 139.7005,
      "locationAddress": "東京都渋谷区道玄坂1丁目",
      "remainingSlots": 1,
      "requiredWorkerCount": 1,
      "minWorkerRating": null,
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

`remainingSlots = required_worker_count − COUNT(assignments WHERE status IN ('accepted','submitted','approved'))`

**投稿カード用のフィールド**（`/api/likes` も同じ `NearbyTask` を返す。組み立ては `app/services/task_card.py`）

| フィールド | 説明 |
|---|---|
| `thumbnailUrl` | 正方形サムネイルの配信URL。未生成なら**参考画像の1枚目で代用**し、それも無ければ `null` |
| `thumbnailSource` | `reference` / `generated` / `streetview` / `placeholder` |
| `badges` | 優先順位の高い順の配列。`sold`（取引終了）> `hot`（閲覧20以上）> `new`（24時間以内）。カードは先頭1つだけを表示する |
| `likeCount` / `isLiked` | いいねの数と、自分が押しているか |
| `viewCount` | 詳細を開かれた回数（オーナー自身の閲覧は数えない） |
| `isMine` | 自分が出した依頼か。`true` のときハートは出さない |

> `sold` と `new` は排他。取引終了済みに NEW は付けない（古い募集に見えないようにするため）。

---

### 3.4 `GET /api/tasks/{taskId}` — 依頼詳細

依頼のオーナー（`client_id` が自分）か、それ以外（撮影する側）かで返す内容を変える。
**オーナー以外が開いたときだけ `view_count` を +1 する。**

**共通部分**: `id` `title` `description` `location*` `scheduledAt` `deadlineAt` `rewardAmount`
`requiredWorkerCount` `approvedWorkerCount` `remainingSlots` `minWorkerRating` `status`
`reviewSummary` `referenceImages[]` `createdAt` `owner` `thumbnailUrl` `badges`
`likeCount` `isLiked` `viewCount` `isMine`

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
  { "step": "published",  "label": "依頼公開",       "status": "done",    "at": "2026-05-24T10:30:00+09:00" },
  { "step": "accepted",   "label": "ワーカーが受注", "status": "done",    "at": "..." },
  { "step": "in_survey",  "label": "現地調査中",     "status": "current", "at": null },
  { "step": "submitted",  "label": "結果提出",       "status": "pending", "at": null },
  { "step": "completed",  "label": "完了",           "status": "pending", "at": null }
]
```
`status` は `done` / `current` / `pending` の3値。日時が入った段階までを `done` とし、
**最初の未達成ステップだけ `current`**、以降は `pending` にする。

**オーナー以外のとき追加**
- `distanceKm`: クエリ `lat` / `lng` があれば計算する
- `myAssignment`: 自分の受注状況（無ければ `null`）
  `{ id, status, retakeCount, remainingRetakes, latestSubmissionId }`

> **撮影する側には他ワーカーの提出画像も `timeline` も返さない。**

---

### 3.4.1 `GET /api/users/{userId}/public` — 公開プロフィール（閲覧用）

依頼詳細の依頼主行から遷移する閲覧専用ページ用（画面⑪）。
**ロールによる出し分けはなく、ログインしていれば誰でも参照できる**
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
    "trustScore": 92.0,
    "approvedSubmissionCount": 8,
    "averageRating": 4.6,
    "reviewCount": 5
  }
}
```

- `404 USER_NOT_FOUND`: 存在しないユーザー
- `asRequester.completionRate` は母数0のとき `null`
- `asWorker.trustScore` は 0〜100 のまま返す（画面はゲージで表示する）
- `asWorker.averageRating` は依頼者から受けた星の平均（1〜5）。評価が無ければ `null`
- 実績が0の側も省略せず返す（表示側で空状態を出す）

**公開してはならない項目**（実装は `app/services/user_service.py` に集約する）

| 項目 | 理由 |
|---|---|
| `email` / `login_id` | 個人情報・認証情報 |
| 却下（`rejected`）・審査中（`screening`）・情報補足待ち（`needs_info`）の依頼 | 却下件数が見えると「危険な依頼を出した人」と特定でき名誉に関わる。未公開の下書き相当 |
| 平均報酬 | 依頼者にとって相場を見られる不利がある（値下げ圧力・相場の固定化） |
| 依頼の本文・位置情報 | 個別の依頼詳細で足りる。プロフィールで束ねると行動追跡に使える |
| 評価コメントの投稿者 | ワーカー本人にも誰が書いたかは伏せる |

統計の母数は**一度でも公開された依頼**（`PUBLIC_TASK_STATUSES`）、すなわち
`status IN ('open','in_progress','completed','expired','cancelled')`。

---

### 3.5 `POST /api/tasks/{taskId}/accept` — 受注

画面⑤に対応。リクエストボディなし。

**処理（1トランザクション）**
1. `SELECT ... FOR UPDATE` で tasks をロック。
2. 自分が出した依頼 → `403 CANNOT_ACCEPT_OWN_TASK`。
3. `status` が `open` / `in_progress` 以外 → `409 INVALID_STATE`。
4. `deadline_at` 超過 → `409 INVALID_STATE`。
5. 依頼者が `minWorkerRating` を指定していて、**評価があり**かつ平均がそれ未満
   → `403 RATING_REQUIREMENT_NOT_MET`。評価が1件も無いワーカーは通す
   （足切りすると評価を得る機会が無く、条件付き依頼が誰にも受けられなくなるため）。
6. 同一ワーカーの assignment の扱い
   - `accepted` / `submitted` → `409 ALREADY_ACCEPTED`
   - **`cancelled`（辞退済み）→ 受け直せる。** 既存の行を `accepted` へ戻す
     （`(task_id, worker_id)` に一意制約があるため新しい行は作らない）。
     **`retake_count` は引き継ぐ**（辞退→受け直しで再撮影の上限をやり直せてしまうと
     D-08 の上限が意味を失うため）
   - `approved` / `failed` / `expired` → `409 ALREADY_ACCEPTED`
7. 空き枠なし → `409 TASK_FULL`。
8. assignment を `accepted` で作成（または再開）。tasks を `in_progress` に更新。
9. 依頼者へ `task_accepted` のお知らせを作成する。

**レスポンス `201`**
```json
{
  "assignment": { "id": "uuid", "taskId": "uuid", "status": "accepted", "retakeCount": 0, "remainingRetakes": 2 }
}
```

---

### 3.5.1 `POST /api/tasks/{taskId}/withdraw` — 受注辞退

**撮影を一度でも提出したら辞退できない**（`409 INVALID_STATE`）。
`assignment.status` が `accepted` かつ提出0件のときだけ許可する。

- assignment を `cancelled` にし、`completed_at` を記録する。
- 有効な受注が0件になり、かつ期限内なら依頼を `open` へ戻す（枠の再開放）。
- **レスポンス `200`**: `{ "assignment": { …3.5 と同じ形 } }`

---

### 3.5.2 `POST /api/tasks/{taskId}/extend-deadline` — 提出期限の延長

オーナーのみ。**後ろへ延ばすことしかできない。**

**リクエスト**: `{ "deadlineAt": "2026-05-29T18:00:00+09:00" }`

| 条件 | 結果 |
|---|---|
| `status` が `open` / `in_progress` 以外 | `409 INVALID_STATE` |
| 既に期限を過ぎている | `409 INVALID_STATE` |
| 新しい期限が現在の期限以前 | `400 VALIDATION_ERROR` |
| 新しい期限が現在時刻以前 | `400 VALIDATION_ERROR` |

**レスポンス `200`**: `{ "task": { …TaskSummary } }`

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
| `deviceInfo` | string(JSON) | | userAgent、プラットフォーム、画面サイズ、`captureMode` |

**バリデーション（同期・API内）**
1. assignment が存在し、リクエスト元が所有者か → 否なら `403`。
2. assignment.status が `accepted` か → 否なら `409 INVALID_STATE`。
3. `retake_count > MAX_RETAKE_COUNT` → `409 RETAKE_LIMIT_EXCEEDED`。
4. `capturedAt` とサーバー時刻の差が `CAPTURE_FRESHNESS_SECONDS`(600s) 超 → `400`（撮り置き画像の投稿を防ぐ）。
5. ファイル形式・サイズ検証。

**処理**
1. 原本を `STORAGE_BUCKET_RAW` に保存（キー: `{taskId}/{assignmentId}/{attemptNo}.jpg`）。
2. EXIF抽出（失敗しても続行）。
3. submissions を `attempt_no = retake_count + 1`、`ai_validation_status='pending'` で作成。
4. assignment を `submitted` に更新。
5. **明示的に `commit()` してから** `BackgroundTasks` に検品パイプラインを登録し、`202` を返す。
   （コミットを依存の後片付けに任せると、検品側から提出レコードが見えないことがある）

**レスポンス `202 Accepted`**
```json
{
  "submission": { "id": "uuid", "attemptNo": 1, "aiValidationStatus": "pending" },
  "pollUrl": "/api/submissions/{id}"
}
```

---

### 3.7 `GET /api/submissions/{submissionId}` — 検品結果のポーリング

画面⑦⑧に対応。参照できるのは**提出したワーカー本人**と**依頼のオーナー**のみ。
フロントは段階的バックオフでポーリングし、`aiValidationStatus` が `pending`/`processing` 以外に
なったら停止する（`docs/05-frontend.md` 画面⑦）。

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
    "framingOk": true,
    "subjectPresent": true,
    "locationVerified": true,
    "privacyMasked": false
  },
  "issues": [
    { "code": "ANGLE_MISMATCH", "message": "対象を中央に収めて撮り直してください" }
  ],
  "retake": { "allowed": true, "remaining": 1 },
  "assignmentStatus": "accepted",
  "workerReview": null
}
```

- `approved` のとき: `processedImageUrl` にマスキング済み画像の署名URL、`issues` は空、`retake.allowed` は false。
- `rejected` かつ再撮影上限到達のとき: `retake.allowed = false`、`assignmentStatus = "failed"`。
- `error` のとき: `retake.allowed = true`（回数は消費されない）。`issues` に `OTHER` を1件入れる。
- `workerReview` は依頼者が評価済みなら入る（ワーカー本人も自分への評価を見られる）。

**画面⑦のチェック項目とのマッピング**

| 画面表示 | レスポンスのキー | 由来 |
|---|---|---|
| 構図確認 | `checks.framingOk` | `ai_feedback.checks.framing_ok` |
| 対象物確認 | `checks.subjectPresent` | `ai_feedback.checks.subject_present` |
| 位置・時刻確認 | `checks.locationVerified` | `location_check.within_tolerance && timestamp_consistent` |
| 顔 / ナンバー保護 | `checks.privacyMasked` | `masking_result.regions` が1件以上 |

---

### 3.7.1 `POST /api/submissions/{submissionId}/review` — ワーカー評価

画面⑩から依頼者が付ける。

**リクエスト**
```json
{ "rating": 5, "tags": ["as_requested", "clear_photo"], "comment": "指定どおりで助かりました" }
```

| フィールド | 制約 |
|---|---|
| `rating` | 1〜5（必須） |
| `tags` | `as_requested` / `clear_photo` / `fast_response` / `accurate_location` から最大4件・重複不可 |
| `comment` | 500文字以内。空白のみは `null` に正規化する |

| 条件 | 結果 |
|---|---|
| 依頼者本人でない | `403 FORBIDDEN` |
| 提出が `approved` でない | `409 INVALID_STATE` |
| 既に評価済み | `409 REVIEW_ALREADY_EXISTS` |

**レスポンス `201`**: `{ "id", "submissionId", "workerId", "rating", "tags", "comment", "createdAt" }`

#### `GET /api/users/me/reviews` — 自分が受け取った評価

**レスポンス `200`**
```json
{
  "reviews": [
    { "id": "uuid", "submissionId": "uuid", "taskId": "uuid", "taskTitle": "駅前の…",
      "rating": 5, "tags": ["as_requested"], "comment": "…", "createdAt": "…" }
  ],
  "averageRating": 4.6,
  "reviewCount": 5
}
```

**`reviewerId` は含めない。** 誰が付けたかはワーカーに見せない。

---

### 3.8 `GET /api/tasks/{taskId}/results` — 結果閲覧（画面⑨⑩）

オーナーのみ。`ai_validation_status='approved'` の submission のみを返す
（D-07により、全員の完了を待たず**合格した順に随時追加される**）。

**レスポンス `200`**
```json
{
  "taskId": "uuid",
  "status": "completed",
  "resultSummary": "駅前の工事は基礎工事の段階で、歩道側に仮囲いが設置されています。",
  "approvedCount": 1,
  "requiredWorkerCount": 1,
  "results": [
    {
      "submissionId": "uuid",
      "processedImageUrl": "https://.../signed",
      "capturedAt": "2026-05-28T13:42:00+09:00",
      "capturedLat": 35.6595,
      "capturedLng": 139.7005,
      "locationLabel": "東京都渋谷区道玄坂1丁目",
      "realityScore": 92,
      "aiSummary": "工事箇所の全体と仮囲いの位置が確認できます。",
      "locationCheck": { "distance_m": 42.5, "within_tolerance": true, "flags": [] },
      "worker": {
        "id": "uuid",
        "displayName": "山田 太郎",
        "trustScore": 96.0,
        "avatarUrl": "/api/users/<uuid>/avatar?v=1f2e3d4c5b6a7890"
      },
      "workerReview": null
    }
  ]
}
```

- `worker.trustScore` は **0〜100 のまま**返す。画面はゲージ（最大値100）で表示するため、5段階への換算は行わない。
- `avatarUrl` は 3.0.1 の配信URL（未設定なら `null`）。
- `locationCheck` は保存された jsonb をそのまま返す（キーは snake_case）。画面⑩で内訳を展開表示する。
- `resultSummary` はデモ期の固定文が残っている場合のみ、この取得時に画像から作り直す。

---

### 3.9 `POST /api/tasks/{taskId}/cancel` — 依頼取消

`status` が `screening` / `needs_info` / `open` のときのみ許可。
`in_progress`（受注済み）の場合は `409 INVALID_STATE` とし、**受注済みワーカーが不利益を被らないようにする。**

---

### 3.10 いいね `/api/tasks/{taskId}/like` `/api/likes`

投稿カード右上のハートに対応する。

- `POST` / `DELETE` はどちらも**冪等**。二重タップでも件数はずれない（一意制約違反は握りつぶす）。
- 自分が出した依頼にはいいねできない → `403 CANNOT_LIKE_OWN_TASK`
  （受注できない依頼をいいね欄に溜めないため）。
- `tasks.like_count` に集計値を持たせ、一覧で件数を引くためのN+1を避ける。

**レスポンス `200`**（付けた場合・取り消した場合ともに同じ形）
```json
{ "taskId": "uuid", "liked": true, "likeCount": 3 }
```

`GET /api/likes` は**いいねした順（新しい順）**で投稿カード（`NearbyTask`）を返す。
`distanceKm` は中心座標が無いため `null`。取引終了（`completed`）した依頼も一覧から消さず、
`badges` に `sold` を付けて返す。

---

### 3.11 保存した検索条件 `/api/saved-searches`

**`POST` リクエスト**

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `label` | string | | 一覧に出す名前（60文字以内）。未指定なら「〈住所〉 から5km」を自動生成 |
| `centerLat` / `centerLng` | number | ✓ | 検索の中心 |
| `locationAddress` | string | | 検索に使った住所（表示用・200文字以内） |
| `radiusKm` | number | | 0.5〜50（既定5） |
| `sort` | string | | `distance` / `reward` / `deadline`（既定 `distance`） |

- 1ユーザーあたり20件まで。超過は `409 SAVED_SEARCH_LIMIT`。
- `lastMatchCount` には**一覧を開いた時点の該当件数**を入れて返す（`GET` のたびに再計算する）。
- 他ユーザーの条件は削除できない（`403 FORBIDDEN`）。

---

### 3.12 お知らせ `/api/notifications`

`GET /api/notifications` は自分宛てを**新しい順に最大50件**返す。

```json
{
  "notifications": [
    {
      "id": "uuid",
      "type": "submission_retake",
      "title": "再撮影が必要です",
      "body": "「駅前の再開発工事の調査」の提出が不合格でした。残り再撮影回数: 1回。",
      "taskId": "uuid",
      "submissionId": "uuid",
      "readAt": null,
      "createdAt": "2026-05-28T13:50:00+09:00"
    }
  ]
}
```

- `GET /api/notifications/unread-count` → `{ "count": 3 }`（タブのバッジ用。30秒間隔で取得する）
- `POST /api/notifications/{id}/read` / `POST /api/notifications/read-all` → `204 No Content`
- 他人のお知らせを既読にしようとすると `404 NOTIFICATION_NOT_FOUND`（存在を教えない）
- 通知の種類と発火元は `docs/02-database.md` 2.8 の表を参照

---

## 4. バックグラウンド処理

### 4.1 BackgroundTasks（リクエストに紐づく）

| 起点 | 処理 | 実装 |
|---|---|---|
| `POST /api/submissions` | 検品パイプライン（機能B・C・D） | `submission_pipeline.run_validation()` |
| `POST /api/tasks` / `duplicate` / `resubmit` | サムネイル生成（機能E）。**`open` になったときだけ** | `thumbnail_service.generate_for_task()` |

どちらも**独立したセッション**を張り、APIのトランザクションとは分離する。
失敗しても呼び出し元のレスポンスには影響しない。

### 4.2 期限超過タスクのクローズ（APScheduler）

`app/jobs/expire_tasks.py` を **5分ごと**に実行する（`EXPIRE_JOB_INTERVAL_MINUTES`）。

**処理**
1. `deadline_at < now()` かつ `status IN ('open','in_progress','needs_info','screening')` を抽出。
2. 未完了の assignment（`accepted` / `submitted`）を `expired` に更新。
3. `approved_worker_count > 0` なら `completed`、そうでなければ `expired` に更新。
4. 依頼者へ `task_completed` / `task_expired` のお知らせを作成する。

FastAPIの `lifespan` でスケジューラを起動・停止する。**起動直後にも1回実行**し、
停止中に期限切れになったタスクを回収する。

> **物理削除は行わない。** 掲示板からの「削除」は `status` による絞り込みで表現する
> （監査ログと合格済み取引を保全するため）。
