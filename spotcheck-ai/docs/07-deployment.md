# 07. デプロイ（Google Cloud Run）

スマホや他の人の端末から開けるようにするための構成と手順。
**撮影（カメラ）と現在地の取得はHTTPSでないとブラウザが拒否する**ため、
HTTPSのURLが自動で付く Cloud Run を使う。

---

## 0. デプロイの経路（**main = 本番**）

**`main` にマージされたものが、そのまま本番のURLになる。**
GitHub Actions（`.github/workflows/deploy.yml`）が `main` への push を検知して自動でデプロイする。

```
feature ブランチ ──PR──▶ dev ──PR（人間の確認が必要）──▶ main ──自動──▶ Cloud Run（本番）
```

| | |
|---|---|
| いつ動くか | `main` に push され、かつ `spotcheck-ai/backend/**` `spotcheck-ai/frontend/**` `spotcheck-ai/deploy/**` `deploy.yml` のいずれかが変わったとき |
| ドキュメントだけの変更 | **動かない**（`paths` フィルタで除外している） |
| 手動実行 | GitHub の Actions タブ →「Deploy to Cloud Run」→ Run workflow |
| 同時実行 | `concurrency: deploy-production` で1本に直列化される |
| タイムアウト | 45分 |
| 実行順 | **DBマイグレーション → バックエンド → フロントエンド → 疎通確認** |

マイグレーションを**デプロイより先**に流すのは、テーブルが無い状態で新しいコードが起動すると
500 を返し続けるため。逆順にしてはいけない。

マイグレーション用の依存は `pyproject.toml` から自動生成する（`ultralytics` だけ除く。
PyTorch を数GB引いてくるが、マイグレーションには不要）。手書きの一覧にしないのは、
将来 `app/models` や `app/core/config` に import が増えたときに気づけないまま壊れるため。

疎通確認（`/api/health` と `/login` が 200 を返すか）まで通って初めて成功扱いになる。
失敗した場合、Cloud Run は**直前のリビジョンで動き続ける**ので、本番が落ちたままにはならない。

> **`dev` の内容は本番に出ていない。** 本番へ出すには `dev` → `main` の PR を出してマージする。
> `CLAUDE.md` §6 のとおり、`main` へのマージは人間の確認が必要。

### 0.1 認証方式（Workload Identity 連携）

サービスアカウントの鍵ファイルを GitHub に置かず、GitHub が発行する OIDC トークンを
Google Cloud 側で検証して権限を渡す。**流出して困る長期鍵が存在しない。**

このリポジトリからの実行だけを許可する条件を、プロバイダ側に付けてある。

```
--attribute-condition="assertion.repository=='Syooosuke/AI-HACK-2026'"
```

デプロイ用サービスアカウント: `github-deployer@<PROJECT_ID>.iam.gserviceaccount.com`
（権限は `run.admin` / `cloudbuild.builds.editor` / `artifactregistry.writer` /
`iam.serviceAccountUser` / `storage.admin`）

### 0.2 GitHub 側に必要な設定

**Secrets**（`Settings` → `Secrets and variables` → `Actions`）

| 名前 | 内容 |
|---|---|
| `GCP_WIF_PROVIDER` | `projects/<番号>/locations/global/workloadIdentityPools/github/providers/github-provider` |
| `GCP_SERVICE_ACCOUNT` | デプロイ用サービスアカウントのメールアドレス |
| `DATABASE_URL` | Supabase の接続文字列（`postgresql+psycopg://`） |
| `JWT_SECRET` | 本番用の鍵。ローカルの開発用と別にする |
| `SUPABASE_URL` / `SUPABASE_SECRET_KEY` | Storage 用 |
| `ORCA_API_KEY` | OrcaRouter |
| `GOOGLE_MAPS_SERVER_API_KEY` | サーバー用キー（リファラ制限なし・IPで制限） |
| `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY` | ブラウザ用キー（リファラ制限あり） |

**Variables**（秘密でないもの。ログに出ても問題なく、変更履歴が追える）

| 名前 | 内容 |
|---|---|
| `FRONTEND_URL` | フロントの URL。バックエンドの `CORS_ORIGINS` に使う |
| `ORCA_STUB_MODE` | `true` / `false` |
| `ORCA_MODEL_TASK_REVIEW` ほか5つ | 用途ごとのモデル指定（`docs/04-ai-pipeline.md` 1.2） |
| `ORCA_REVIEW_JURY` / `ORCA_VALIDATION_JURY` / `ORCA_VALIDATION_BOUNDARY` | 冗長化（多数決）の設定 |

**モデルの割り当てを Secrets ではなく Variables に置いているのは、変更履歴を追えるようにするため。**
秘密情報ではないうえ、「いつからどのモデルに切り替えたか」が事故調査で効く。

> ワークフローは**空文字の環境変数を Cloud Run へ渡さない**。
> 未設定の項目はアプリ側の既定へ落ち、既存の設定を消してしまうこともない。

これらは `deploy/env.sh` と同じ値。**ローカルの `deploy/env.sh` を更新したら、GitHub 側も更新する。**

---

## 1. 構成

| レイヤ | 置き場所 | 設定 |
|---|---|---|
| フロントエンド | Cloud Run（`spotcheck-frontend`） | メモリ1Gi / max-instances 5。Next.js standalone |
| バックエンド | Cloud Run（`spotcheck-backend`） | メモリ2Gi / CPU2 / timeout 900s / concurrency 20 / max-instances 3 |
| DB | **Supabase の PostgreSQL** | Cloud SQL は使わない（無料枠で足りるため） |
| 画像ストレージ | Supabase Storage | ローカル開発と同じ |

> **Cloud SQL を使わない理由**: 無料枠が無く月$10前後かかる。Supabase の PostgreSQL は
> すでに Storage で契約しており、無料枠で足りる。

**バックエンドの timeout を 900秒にしているのは、検品が実測30秒〜15分かかるため。**
ただし検品自体は `BackgroundTasks` で走り、APIは即座に `202` を返す。

### 1.1 イメージ

| | 内容 |
|---|---|
| バックエンド | `python:3.13-slim`。OpenCV 用に `libgl1` / `libglib2.0-0` を入れる |
| | **CPU版 PyTorch を先に入れる。** ultralytics は既定でCUDA付き torch を引くが、Cloud Run はGPUを持たないため数GBのCUDAライブラリが完全に無駄になる |
| | 重み（`models_weights/*.pt`）はイメージへ焼き込む。無い場合はマスキングをスキップして動く |
| フロントエンド | `node:22-slim` の3段ビルド。`output: "standalone"` で実行イメージを小さくする |
| | `NEXT_PUBLIC_*` を `ARG` → `ENV` で受け、**ビルド時に埋め込む** |

どちらも Cloud Run が渡す `$PORT`（既定8080）で待ち受ける。

### 1.2 接続プールへの対応（`app/core/db.py`）

本番は Supabase の transaction pooler（PgBouncer, 6543番）を経由する。
このモードでは1トランザクションごとに背後の接続が切り替わるため、
psycopg3 の**サーバー側プリペアドステートメントを無効化**している（`prepare_threshold=None`）。

無効化しないと次のエラーが出る。psycopg3 は既定で同じSQLを5回実行するとプリペアドに切り替えるため、
**最初の数回は成功し、その後だけ失敗する**という分かりにくい壊れ方をする。

```
psycopg.errors.InvalidSqlStatementName: prepared statement "_pg3_1" does not exist
```

直接接続（ローカル開発）でも無効のままで問題なく、失うのは小さな最適化だけ。

### 費用の目安

- Cloud Run: 月200万リクエストまで無料。デモ用途なら実質無料
- Maps Platform: SKUごとの無料枠あり（条件は変わるためコンソールで確認）
- 新規アカウントの $300 / 90日トライアルクレジットがあれば、いずれも十分カバーできる

---

## 2. 事前準備

### 2.1 gcloud CLI

```bash
brew install --cask google-cloud-sdk
gcloud auth login          # ブラウザが開く（対話的なので手元で実行する）
gcloud projects list       # PROJECT_ID を確認
```

### 2.2 Supabase の接続文字列

Supabase Dashboard → **Project Settings** → **Database** → **Connection string** → **URI**。
取得した文字列の `postgresql://` を **`postgresql+psycopg://`** に置き換える（SQLAlchemy のドライバ指定）。

```
postgresql+psycopg://postgres.xxxx:PASSWORD@aws-0-ap-northeast-1.pooler.supabase.com:6543/postgres
```

> パスワードに `@` `:` `/` などが含まれる場合はURLエンコードする。

### 2.3 設定ファイル

```bash
cd spotcheck-ai
cp deploy/env.example.sh deploy/env.sh   # deploy/env.sh は .gitignore 済み
```

`deploy/env.sh` に値を入れる。`JWT_SECRET` は必ず新しく生成する（ローカルの開発用鍵を使わない）。

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

### 2.4 APIの有効化（初回のみ）

```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
```

---

## 3. マイグレーションとシード

自動デプロイはマイグレーションを流すが、**シード（デモアカウント）は流さない。**
初回だけローカルから実行する。

```bash
cd backend
DATABASE_URL="<deploy/env.sh と同じ値>" ./.venv/bin/alembic upgrade head
DATABASE_URL="<同じ値>" ./.venv/bin/python -m scripts.seed_demo_users
DATABASE_URL="<同じ値>" ./.venv/bin/python -m scripts.seed_demo_tasks   # 任意
DATABASE_URL="<同じ値>" ./.venv/bin/python -m scripts.init_storage      # バケット作成
```

> ローカルのDBとは別なので、**デモアカウントの投入を忘れるとログインできない。**

---

## 4. 手動デプロイ（**通常は使わない**）

**普段は `main` へのマージで自動デプロイされる（0節）。** 以下は次の場合にだけ使う。

- GitHub Actions が使えないとき（障害・権限切れ）
- 未マージのブランチを本番URLで試したいとき（**本番が上書きされるので注意**）

手元からデプロイすると `main` の内容と本番がずれる。実行したら、その旨を共有すること。

```bash
cd spotcheck-ai
./deploy/deploy.sh            # バックエンド → フロントの順に両方
./deploy/deploy.sh backend    # バックエンドのみ
./deploy/deploy.sh frontend   # フロントのみ
```

- バックエンドは PyTorch を含むため、**初回ビルドに10分前後**かかる（CPU版に固定してイメージは約2.3GB）
- フロントは `NEXT_PUBLIC_*` を**ビルド時に埋め込む**ため、APIのURLや地図キーを変えたら再デプロイが必要

### 4.0 実装上の注意（つまずいた点）

| 問題 | 対処 |
|---|---|
| `--set-env-vars` が `DATABASE_URL` の `@` と衝突して構文エラー | 環境変数は **YAMLファイル**（`--env-vars-file`）で渡す |
| Artifact Registry 作成の確認プロンプトで停止 | `--quiet` を付ける |
| `$VAR）` のように直後が全角括弧だと変数名を誤認 | `${VAR}` で囲む |
| **`--build-env-vars` は Docker の `--build-arg` に渡らない** | `frontend/cloudbuild.yaml` を用意し、`gcloud builds submit` で `--build-arg` として渡してから `gcloud run deploy --image` する |

最後の点は特に分かりにくい。渡らないと `NEXT_PUBLIC_*` が**空文字で埋め込まれ**、
APIの呼び先が同一オリジンになり（Next側に該当APIは無いので404）、地図キーも消える。
デプロイ後は必ず**JSバンドルにURLとキーが入っているか**を確認する。

```bash
curl -s https://<フロントのURL>/login | grep -o '/_next/static/chunks/[^"]*\.js' | head -5
# 出てきたチャンクを取得し、バックエンドのURLと "AIza" が含まれることを確認する
```

### 4.1 デプロイ後に必ずやること

1. **CORS にフロントのURLを設定**

```bash
gcloud run services update spotcheck-backend --region asia-northeast1 \
  --update-env-vars CORS_ORIGINS=https://spotcheck-frontend-xxxx.run.app
```

2. **Google Maps キーのリファラー制限**に `https://spotcheck-frontend-xxxx.run.app/*` を追加

---

## 5. 確認

### 5.1 実際のデプロイ結果（2026-08-12）

| サービス | URL |
|---|---|
| フロントエンド | https://spotcheck-frontend-dathtekrwq-an.a.run.app |
| バックエンド | https://spotcheck-backend-dathtekrwq-an.a.run.app |

- プロジェクト: `gmp-demo-project-770876903`（課金が有効なプロジェクト）
- リージョン: `asia-northeast1`
- DB: Supabase PostgreSQL 17.6（`aws-0-ap-northeast-2.pooler.supabase.com:6543`）
- 画面6種すべて200、ログイン・投稿一覧4件・サムネイル配信（99KB）を確認

デモ用のQRコードは `deploy/make_qr.py` で作る（`docs/assets/demo-qr.png`）。

### 5.2 確認手順

```bash
curl -s https://spotcheck-backend-xxxx.run.app/api/health | python3 -m json.tool
```

`status` が `degraded` の場合は `configWarnings` に不足している環境変数が出る。

ブラウザ（スマホ含む）でフロントのURLを開き、次を確認する。

- ログイン（`yamada` / `spotcheck123`）
- ホームに投稿が並ぶ・サムネイルが出る
- 「さがす」で地図と地名検索
- 依頼作成でストリートビュー
- **撮影画面でカメラが起動する**（HTTPSなので動く）
- お知らせタブに通知が届く

---

## 6. 費用と安全策（デモURLを共有する前に）

URLを共有すると、アクセス数に応じて課金されうる。以下を実際に設定してある。

| 対策 | 設定値 | コマンド |
|---|---|---|
| APIキーの分離 | ブラウザ用とサーバー用（Street View Static のみ）を別キーにする | `gcloud services api-keys create --api-target=service=street-view-image-backend.googleapis.com` |
| リファラー制限 | 本番URLと `localhost:3000/*` のみ | `gcloud services api-keys update <UID> --allowed-referrers="..."` |
| APIの絞り込み | Maps JS / Geocoding / Places (New) / Street View のみ | `--api-target=service=...` を複数指定 |
| 1日あたりの上限 | Geocoding・Places・Street View 各1,000／日、Maps JS 3,000／日 | `gcloud quotas preferences create --quota-id=BillableDefaultPerDayPerProject --preferred-value=1000` |
| 最大インスタンス数 | backend 3 / frontend 5 | `gcloud run services update <SERVICE> --max-instances=3` |
| 予算アラート | $10 で 50% / 90% / 100% 通知 | `gcloud billing budgets create --budget-amount=10 --threshold-rule=percent=0.5` |

**キーはブラウザに露出する**（`NEXT_PUBLIC_*` はJSに焼き込まれるため原理的に隠せない）。
リファラー制限・APIの絞り込み・1日上限が防御線になる。

> Places API の1日上限は `BillableDefaultPerDayPerProject` が存在しないため、
> `AutocompletePlacesRequestPerDayPerProject` と `GetPlaceRequestPerDayPerProject` を個別に設定する。

**OrcaRouter の課金にも注意する。** 用途ごとにモデルを指定し、合議を有効にしているため、
1件の依頼審査で最大3回、境界にかかった検品でさらに2回の呼び出しが発生する
（`docs/04-ai-pipeline.md` 1.2）。デモ前に温存したい場合は `ORCA_STUB_MODE=true` にする。

### サーバー用キーを分ける理由

ブラウザ用キーにリファラー制限を掛けると、**リファラーを送らないサーバーからの呼び出しは拒否される**。
分けずに運用すると、制限を入れた瞬間にサムネイル生成（Street View Static）が止まる。

---

## 7. 運用上の注意

| 項目 | 内容 |
|---|---|
| コールドスタート | バックエンドはYOLO同梱で初回応答に数十秒かかることがある。発表前は `BACKEND_MIN_INSTANCES=1` にして温めておく。フロント側も GET を1回だけ再試行して吸収する（`lib/api/client.ts`） |
| 秘密情報 | `deploy/env.sh` はコミットしない。より厳密にやるなら Secret Manager へ移す |
| ログ | `gcloud run services logs read spotcheck-backend --region asia-northeast1 --limit 50` |
| AI呼び出しの追跡 | `ai_invocations` テーブルに purpose / model / latency / error が残る（`docs/02-database.md` 2.7） |
| ロールバック | Cloud Run はリビジョン管理されるため、コンソールから前のリビジョンへトラフィックを戻せる |
| 削除 | `gcloud run services delete spotcheck-backend spotcheck-frontend --region asia-northeast1` |
