# 07. デプロイ（Google Cloud Run）

スマホや他の人の端末から開けるようにするための構成と手順。
**撮影（カメラ）と現在地の取得はHTTPSでないとブラウザが拒否する**ため、
HTTPSのURLが自動で付く Cloud Run を使う。

---

## 1. 構成

| レイヤ | 置き場所 | 備考 |
|---|---|---|
| フロントエンド | Cloud Run（`spotcheck-frontend`） | Next.js standalone。HTTPSのURLが自動発行される |
| バックエンド | Cloud Run（`spotcheck-backend`） | FastAPI。YOLO同梱のためメモリ2Gi |
| DB | **Supabase の PostgreSQL** | Cloud SQL は使わない（無料枠で足りるため） |
| 画像ストレージ | Supabase Storage | ローカル開発と同じ |

> **Cloud SQL を使わない理由**: 無料枠が無く月$10前後かかる。Supabase の PostgreSQL は
> すでに Storage で契約しており、無料枠で足りる。

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

## 3. マイグレーション

Cloud Run へ上げる前に、Supabase の DB へスキーマを作る。**ローカルから実行する。**

```bash
cd backend
DATABASE_URL="<deploy/env.sh と同じ値>" ./.venv/bin/alembic upgrade head
DATABASE_URL="<同じ値>" ./.venv/bin/python -m scripts.seed_demo_users
DATABASE_URL="<同じ値>" ./.venv/bin/python -m scripts.seed_demo_tasks   # 任意
```

> ローカルのDBとは別なので、**デモアカウントの投入を忘れるとログインできない。**

---

## 4. デプロイ

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

### 5.2 確認手順

```bash
curl -s https://spotcheck-backend-xxxx.run.app/api/health | python3 -m json.tool
```

ブラウザ（スマホ含む）でフロントのURLを開き、次を確認する。

- ログイン（`yamada` / `spotcheck123`）
- ホームに投稿が並ぶ・サムネイルが出る
- 「さがす」で地図と地名検索
- 依頼作成でストリートビュー
- **撮影画面でカメラが起動する**（HTTPSなので動く）

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

### サーバー用キーを分ける理由

ブラウザ用キーにリファラー制限を掛けると、**リファラーを送らないサーバーからの呼び出しは拒否される**。
分けずに運用すると、制限を入れた瞬間にサムネイル生成（Street View Static）が止まる。

---

## 7. 運用上の注意

| 項目 | 内容 |
|---|---|
| コールドスタート | バックエンドはYOLO同梱で初回応答に数十秒かかることがある。発表前は `BACKEND_MIN_INSTANCES=1` にして温めておく |
| 秘密情報 | `deploy/env.sh` はコミットしない。より厳密にやるなら Secret Manager へ移す |
| ログ | `gcloud run services logs read spotcheck-backend --region asia-northeast1 --limit 50` |
| ロールバック | Cloud Run はリビジョン管理されるため、コンソールから前のリビジョンへトラフィックを戻せる |
| 削除 | `gcloud run services delete spotcheck-backend spotcheck-frontend --region asia-northeast1` |
