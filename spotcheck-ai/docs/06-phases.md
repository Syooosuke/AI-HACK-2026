# 06. 実装フェーズと現在地

**方針: デモ優先（D-10）。** 画面フローを最初に一気通貫で通し、その後にAI機能を実際のものへ差し替える。

```
Phase 0  環境構築                                  ✅ 完了
Phase 1  DB＋CRUD API（AIはスタブ）                ✅ 完了
Phase 2  画面①〜⑩の一気通貫（★デモ成立点）        ✅ 完了
Phase 3  依頼審査AIの実装                          ✅ 完了
Phase 4  画像検品AI＋位置偽装対策の実装            ✅ 完了
Phase 5  プライバシー自動マスキングの実装          ✅ 完了
Phase 6  仕上げ（期限ジョブ・決済スタブ・エラー処理）✅ 完了
────────────────────────────────────────────────
Phase 7  デプロイ（Cloud Run / GitHub Actions）    ✅ 完了（docs/07-deployment.md）
Phase 8  運用で見つかった課題への対応              ⏳ 継続中（4節）
```

**Phase 0〜7 は完了している。** 以降の作業は「フェーズ」ではなく個別の課題として Issue で管理する
（`.claude/issue-guidelines.md`）。

---

## 1. 各フェーズの成果物

### Phase 0 — 環境構築

- `frontend/` に Next.js 14（App Router, TypeScript, Tailwind, ESLint）
- `backend/` に FastAPI（`pyproject.toml` に ruff / pytest の設定も同居）
- `docker-compose.yml`（ローカル PostgreSQL）、`.env.example` / `.env.local.example`
- Supabase Storage に2バケット（`submissions-raw` / `submissions-processed`。**どちらも非公開**）
- `GET /api/health` — 依存先の状態と `configWarnings` を返す

**達成した完了条件**
- [x] `npm run dev` と `uvicorn` が同時に起動する
- [x] フロントから `/api/health` を叩いて 200 が返る
- [x] `.env` 未設定でもアプリが起動し、不足している変数を起動ログで警告する

### Phase 1 — DB＋CRUD API（AIはスタブ）

- Alembic マイグレーション（現在7本。`docs/02-database.md` 0節）
- SQLAlchemyモデル・Pydanticスキーマ・リポジトリ層
- ログインID＋パスワードによる認証（D-06）と `deps.py` でのユーザー解決
- ステータス遷移、受注時の `SELECT FOR UPDATE`、再撮影ループのカウント
- 画像アップロードとStorage保存、署名URL発行

**達成した完了条件**
- [x] `alembic upgrade head` が成功し、全テーブルが作成される
- [x] 依頼作成 → 受注 → 提出 → 検品(スタブ) → 合格 までを curl だけで実行できる
- [x] 再撮影ループが仕様通り動く（1回目不合格 → 2回目合格 / 3回不合格で `failed` と枠再開放）
- [x] 受注枠を超えた `accept` が `409 TASK_FULL` を返す
- [x] pytest で状態遷移のテストが通る

### Phase 2 — 画面①〜⑩の一気通貫 ★デモ成立点

- デザイントークンと共通UIコンポーネント
- ログイン・新規登録と `Authorization: Bearer` の自動付与
- 画面①〜⑩の実装（`docs/05-frontend.md`）
- Google Maps 連携（地点ピッカー、近傍タスクのマーカー、地名・住所検索、ストリートビュー）
- 画面⑥のカメラ実装（`getUserMedia` ＋ `watchPosition`、メタデータ同時送信）
- ポーリングによる検品状況の更新

**達成した完了条件**
- [x] 依頼作成 → 受注・撮影 → 検品結果表示 → 結果閲覧 をブラウザ操作のみで完走できる
- [x] 画面⑥で位置情報が取れないときシャッターが押せない
- [x] 再撮影ループが画面上で確認できる（スタブが奇数回目を落とすため必ず1回発生する）
- [x] スマートフォンの実機（HTTPS経由）でカメラとGPSが動作する

> **AI部分がスタブのままでもデモが成立する状態は、以降も維持する。**

### Phase 3 — 依頼審査AIの実装

- `OrcaClient` の実HTTP実装（`docs/04-ai-pipeline.md` 1節）
- `task_review.py` のプロンプトと判定ロジック、`ai_invocations` へのログ記録
- 参考画像がある場合の `tier="vision"` への切替

**達成した完了条件**
- [x] 正常な依頼が `approved` になり公開される
- [x] 情報不足の依頼が `needs_info` になり、`missingInfo` に具体的な補足要求が入る
- [x] 危険な依頼が `rejected` になる
- [x] `needs_info` から補足して再審査すると `approved` に変わる
- [x] `ORCA_STUB_MODE=true` に戻すとスタブで動作する

### Phase 4 — 画像検品AI＋位置偽装対策

- `location_check.py` の C-1〜C-6 と `reality_score`
- `image_validation.py` のVLM検品
- `submission_pipeline.py` の統括処理とトランザクション境界
- EXIF抽出（Pillow）

**達成した完了条件**
- [x] 依頼内容に合った画像が合格し、無関係な画像が `SUBJECT_MISSING` で不合格になる
- [x] 依頼地点から離れた座標で提出すると `LOCATION_MISMATCH` で不合格になる
- [x] `capturedAt` を10分以上前に偽装すると弾かれる
- [x] AI呼び出しを意図的に失敗させると `error` になり、**再撮影回数が消費されない**
- [x] `reality_score` が減点ルール通りに算出される

> **「暗い画像・ブレた画像が不合格になる」という当初の完了条件は取り下げた。**
> 現地で1枚撮るだけのワーカーには達成が難しく、まともな写真が再撮影になっていたため。
> 現在の基準は「対象が判別できるか」であり、**判別できるなら暗くても合格させる**
> （`docs/04-ai-pipeline.md` 3.2）。不合格にするのは黒つぶれ・白飛び・激しいブレで
> **対象が何であるか分からない**場合に限る。

### Phase 5 — プライバシー自動マスキング

- Ultralytics YOLO の導入と重みの配置（`models_weights/`。`.gitignore` 対象）
- 顔検出＋ぼかし、車両検出 → VLMへプレート座標を問い合わせ → 黒塗り
- 表札・番地のVLM座標問い合わせ → ぼかし
- 加工後画像を `submissions-processed` へ保存し `masking_result` を記録

**達成した完了条件**
- [x] 通行人の顔がぼかされ、人物の全身はぼかされていない
- [x] ナンバープレートが黒塗りされる
- [x] 重みファイルが無い環境でも例外を出さずスキップし、ログに警告が出る
- [x] クライアント向けAPIのレスポンスに原本URLが一切含まれない（`test_submission_pipeline.py` で検証）
- [x] 画面⑩でマスキング済み画像のみが表示される

### Phase 6 — 仕上げ

- `expire_tasks.py` と APScheduler（5分間隔＋起動時1回）
- 決済スタブ（合格時に `charge` / `payout` を記録）
- エラーメッセージの日本語化と統一、トースト
- ローディング・スケルトンUI、ポーリングの打ち切り

**達成した完了条件**
- [x] 期限切れタスクが自動で `expired` になり、ワーカー側の一覧から消える
- [x] 合格済み提出がある状態で期限が切れた場合は `completed` になる
- [x] `payments` に charge / payout が1件ずつ記録される
- [x] 主要なエラーがすべて日本語で表示される

> ポーリングの打ち切りは、当初の「60秒」から**15分**へ変更した。
> 実運用の検品は30秒〜15分かかり、60秒では結果が出る前に打ち切られていたため
> （`docs/05-frontend.md` 画面⑦）。

### Phase 7 — デプロイ

Google Cloud Run（フロント／バックエンド）＋ Supabase（DB / Storage）。
`main` への push を GitHub Actions が検知して自動デプロイする。詳細は `docs/07-deployment.md`。

---

## 2. Phase 6 以降に追加した機能

当初の仕様書に無かったもの。いずれも本ドキュメント群へ反映済み。

| 機能 | 追加した理由 | 主な参照先 |
|---|---|---|
| お知らせ（`notifications`） | 検品や審査の結果が非同期で決まるため、画面を開いていないと気づけなかった | 02-database 2.8 / 03-api 3.12 |
| いいね・保存した検索条件 | 気になる依頼を後から見返す導線が無かった | 02-database 2.9〜2.10 / 03-api 3.10〜3.11 |
| 投稿サムネイル（機能E） | 写真の無い依頼が一覧で灰色の四角になっていた | 04-ai-pipeline 6節 |
| 投稿タグ（SOLD / HOT / NEW） | 一覧のどれが新しく・動きがあるのか分からなかった | 05-frontend 6節 |
| ワーカー評価（`worker_reviews`） | `trust_score` は自動計算のみで、依頼者の主観を残す手段が無かった | 02-database 2.11 / 03-api 3.7.1 |
| 受注条件（`min_worker_rating`） | 上の評価を受注のフィルタとして使えるようにした | 02-database 2.2 / 03-api 3.5 |
| 公開プロフィール（画面⑪） | 依頼者→ワーカーの評価だけがあり、逆方向が無かった | 03-api 3.4.1 / 05-frontend 画面⑪ |
| アバター画像 | 表示名だけでは誰か分かりにくい | 03-api 3.0.1 |
| 依頼の複製・期限延長・受注辞退 | 運用で必要になった操作 | 03-api 3.1.2 / 3.5.1 / 3.5.2 |
| 依頼文のAI生成・クイック入力 | 依頼文が書けず `needs_info` で止まる利用者が多かった | 04-ai-pipeline 7.2 / 05-frontend 画面① |
| 決定論フィルタ（`content_filter`） | スタブモードでAI審査が素通りする | 04-ai-pipeline 2.2.1 |
| 用途別モデル指定と合議 | 同じ入力でも判定が振れることを実測した | 04-ai-pipeline 1.2 |

---

## 3. テスト

`backend/tests/` に **294件**（`pytest -q --collect-only` 時点）。
`pytest` は `spotcheck_test` DB を自動作成するため **`docker compose up -d db` が必要**。

| ファイル | 主な検証内容 |
|---|---|
| `test_auth.py` / `test_unified_account.py` | 認証、ロールを持たない権限判定 |
| `test_state_transitions.py` / `test_accept_rules.py` | ステータス遷移、受注競合、辞退と受け直し |
| `test_submission_pipeline.py` | 検品パイプライン全体、**原本URLの非露出**、再撮影ループ |
| `test_validation_boundary.py` | 境界再判定と多数決 |
| `test_task_review.py` / `test_content_filter.py` | 依頼審査の判定と決定論フィルタ |
| `test_location_check.py` | C-1〜C-6 と Reality Score |
| `test_masking.py` | マスキングの適用ロジック（YOLO推論は差し替え） |
| `test_orca_client.py` / `test_model_routing.py` | リトライ・JSON解析・スキーマ正規化・モデル振り分け |
| `test_expire_and_payments.py` | 期限ジョブと決済スタブ |
| `test_notifications.py` / `test_social.py` / `test_worker_reviews.py` | お知らせ・いいね・評価 |
| `test_public_profile.py` / `test_avatar.py` | 公開範囲、アバターの差し替え |
| `test_files_route.py` | **原本バケットの配信拒否** |
| `test_thumbnail.py` | サムネイルのフォールバック段階 |

**既存テストを「通らないから」といって削除・スキップしてはならない。**
仕様変更で期待値が変わった場合のみ、変更理由をコミットメッセージに書いて更新する（`CLAUDE.md` 6.2）。

実モデルを使う比較（`scripts/bench_models.py` / `scripts/bench_task_review.py`）は
**課金が発生するためCIに入れない。** モデルやプロンプトを変えたときに手で流す
（`docs/04-ai-pipeline.md` 1.2）。

---

## 4. 継続中の課題

| 項目 | 状況 |
|---|---|
| OrcaRouter の画像生成API | エンドポイント・ルーター名が未確認。`ORCA_ROUTER_IMAGE` 未設定ならストリートビュー画像を使う（`docs/04-ai-pipeline.md` 6節） |
| 検品の待ち時間 | 実測30秒〜15分。合議を増やすほど伸びるため、境界のみ再判定にとどめている |
| C-5 の日出没判定 | 「6時〜18時を daylight」の簡易判定。季節・緯度は考慮していない |
| 孤児ファイル | 検品失敗時に Storage 上の原本が残る。削除処理は実装していない（許容） |

---

## デモシナリオ

1. クライアントで「駅前の再開発工事の進捗確認」を作成 → **AI審査で公開される**
2. 参考に「隣の家に人がいるか確認してほしい」を作成 → **AIが却下する**（安全性のアピール）
3. 情報不足の依頼を作成 → **AIが補足要求を出す** → 補足して公開
4. ワーカーに切替 → 地図で依頼を発見 → 受注
5. カメラで撮影（GPS・タイムスタンプが画面に出ている状態）→ 提出
6. **不合格なら再撮影指示が具体的に表示される** → 再撮影して合格
   （`ORCA_STUB_MODE=true` なら奇数回目が必ず落ちる）
7. **顔とナンバープレートがマスクされた画像**が生成される
8. クライアントに切替 → 結果画面でAI要約・Reality Score・ワーカー評価を確認
9. お知らせタブに一連の通知が並んでいることを確認

---

## 実装時の注意（再掲）

- `CLAUDE.md` の D-01〜D-10 に反する実装が必要になったら、**必ず作業を止めて人間に確認する。**
- スタブモードは最後まで維持する。デモ当日の障害対策である。
- 原本画像をクライアントに露出させない。この1点はテストで機械的に検証すること。
- `main` は本番。`dev` → `main` のマージは人間の確認が要る（`CLAUDE.md` 6.1）。
