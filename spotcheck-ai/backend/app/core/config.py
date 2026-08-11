"""環境変数の読み込みと設定値の提供。

`.env` が無くてもアプリが起動できるよう、すべての設定にデフォルト値を持たせる。
不足している変数は `collect_config_warnings()` が列挙し、起動時にログへ出力する
（docs/06-phases.md Phase 0 の完了条件）。
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

#: JWT_SECRET 未設定時に開発環境だけで使う固定鍵。
#: 固定値なので uvicorn の再起動を挟んでもログインが切れない（デモ時の利便性のため）。
DEV_JWT_SECRET = "spotcheck-development-only-secret"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- アプリ ---
    app_env: Literal["development", "staging", "production"] = "development"
    api_port: int = 8000
    cors_origins: str = "http://localhost:3000"

    # --- データベース ---
    database_url: str = "postgresql+psycopg://postgres:password@localhost:5432/spotcheck"

    # --- 認証（ログインID＋パスワード / JWT）---
    # 本番では必ず十分に長いランダム文字列を与える。未設定のまま production で起動すると失敗する。
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    # ネイティブアプリのように「一度ログインしたらしばらく維持される」挙動にするため長め
    jwt_expire_days: int = 30
    bcrypt_rounds: int = 12

    # --- Supabase / ストレージ ---
    supabase_url: str = ""
    # 新方式の秘密キー（sb_secret_...）。Storage への管理操作に使う
    supabase_secret_key: str = ""
    # 旧方式（service_role のJWT）。2026年末に廃止予定。上が未設定のときのみ使う
    supabase_service_role_key: str = ""
    storage_bucket_raw: str = "submissions-raw"
    storage_bucket_processed: str = "submissions-processed"
    storage_backend: Literal["auto", "supabase", "local"] = "auto"
    local_storage_dir: str = "./.storage"

    # --- OrcaRouter（docs/04-ai-pipeline.md 1節）---
    orca_api_base_url: str = "https://api.orcarouter.ai/v1"
    orca_api_key: str = ""
    # model に渡すのは「ルーター名」。モデル名をコードへ直書きしない。
    orca_router_light: str = "orcarouter/auto"
    orca_router_vision: str = "orcarouter/auto"
    orca_timeout_seconds: int = 60
    orca_max_retries: int = 2
    orca_stub_mode: bool = False

    # --- 投稿カードのタグ判定 ---
    #: 作成からこの時間以内は NEW タグを出す
    new_task_hours: int = 24
    #: 詳細の閲覧数がこの値以上なら HOT タグを出す
    hot_view_count: int = 20

    # --- 投稿サムネイル ---
    #: Street View Static API 用のサーバー側キー。フロントのキーとは分ける
    #: （フロントのキーはリファラー制限がかかるためサーバーからは使えない）
    google_maps_server_api_key: str = ""
    #: サムネイルの一辺（正方形）
    thumbnail_size: int = 640
    #: 画像生成に使う OrcaRouter のルーター名。未設定ならストリートビュー画像をそのまま使う
    #: TODO(human-decision): 画像生成のルーター名・エンドポイント形式が判明したら設定する
    orca_router_image: str = ""
    #: 画像生成のエンドポイント（OpenAI images 互換を想定）
    orca_images_path: str = "/images/generations"

    # --- 判定パラメータ ---
    task_review_score_threshold: int = 70
    submission_score_threshold: int = 70
    max_retake_count: int = 2
    location_tolerance_meters: float = 100.0
    timestamp_tolerance_seconds: int = 300
    capture_freshness_seconds: int = 600

    # --- 物体検出 ---
    yolo_model_path: str = "./models_weights/yolov8n.pt"
    yolo_face_model_path: str = "./models_weights/yolov8n-face.pt"
    yolo_confidence_threshold: float = 0.35
    blur_kernel_ratio: float = 0.15

    # --- 画像制約 ---
    max_upload_size_mb: int = 15
    allowed_image_types: str = "image/jpeg,image/png,image/webp"

    # ------------------------------------------------------------------
    # 派生値
    # ------------------------------------------------------------------
    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def allowed_image_type_list(self) -> list[str]:
        return [t.strip() for t in self.allowed_image_types.split(",") if t.strip()]

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def supabase_key(self) -> str:
        """Storage 呼び出しに使う秘密キー。新方式を優先し、無ければ旧 service_role を使う。"""
        return self.supabase_secret_key or self.supabase_service_role_key

    @property
    def supabase_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_key)

    @property
    def effective_storage_backend(self) -> Literal["supabase", "local"]:
        """実際に使用するストレージ実装。auto の場合は設定状況から決める。"""
        if self.storage_backend == "auto":
            return "supabase" if self.supabase_configured else "local"
        return self.storage_backend

    @property
    def effective_jwt_secret(self) -> str:
        """JWT の署名鍵。開発時に限り既定値へフォールバックする。

        production で未設定の場合は、推測可能な鍵で運用されることを防ぐため例外を送出する。
        """
        if self.jwt_secret:
            return self.jwt_secret
        if self.app_env == "production":
            raise RuntimeError("JWT_SECRET が未設定です。production では必ず設定してください。")
        return DEV_JWT_SECRET

    @property
    def jwt_expire_seconds(self) -> int:
        return self.jwt_expire_days * 24 * 60 * 60

    @property
    def orca_stub_enabled(self) -> bool:
        """スタブモードで動作するか（docs/04-ai-pipeline.md 1.4）。"""
        return self.orca_stub_mode or not self.orca_api_key


@lru_cache
def get_settings() -> Settings:
    return Settings()


# ----------------------------------------------------------------------
# 起動時の設定チェック
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class ConfigWarning:
    """未設定の環境変数と、その結果アプリがどう振る舞うかの説明。"""

    variables: tuple[str, ...]
    feature: str
    fallback: str

    def format(self) -> str:
        names = ", ".join(self.variables)
        return f"[{self.feature}] {names} が未設定です → {self.fallback}"


def collect_config_warnings(settings: Settings) -> list[ConfigWarning]:
    """不足している環境変数を列挙する。アプリの起動は妨げない。"""
    warnings: list[ConfigWarning] = []

    if not settings.supabase_configured:
        warnings.append(
            ConfigWarning(
                variables=("SUPABASE_URL", "SUPABASE_SECRET_KEY"),
                feature="ストレージ",
                fallback=(
                    f"ローカルファイル保存にフォールバックします（{settings.local_storage_dir}）。"
                    "画像はSupabase Storageに保存されません。"
                ),
            )
        )

    if not settings.orca_api_key:
        warnings.append(
            ConfigWarning(
                variables=("ORCA_API_KEY",),
                feature="AI",
                fallback="OrcaClient はスタブモードで動作します（固定レスポンスを返します）。",
            )
        )
    elif settings.orca_stub_mode:
        warnings.append(
            ConfigWarning(
                variables=("ORCA_STUB_MODE",),
                feature="AI",
                fallback="ORCA_STUB_MODE=true のため、APIキーがあってもスタブ応答を返します。",
            )
        )

    if not settings.jwt_secret:
        warnings.append(
            ConfigWarning(
                variables=("JWT_SECRET",),
                feature="認証",
                fallback=(
                    "開発用の固定鍵でトークンを署名します（誰でも偽造できます）。"
                    "本番相当の環境では必ず設定してください。"
                ),
            )
        )

    # 値の比較ではなく「環境変数（または .env）で与えられたか」で判定する。
    # 既定値と同じ接続先を明示設定した場合に誤って警告しないようにするため。
    if "database_url" not in settings.model_fields_set:
        warnings.append(
            ConfigWarning(
                variables=("DATABASE_URL",),
                feature="DB",
                fallback=(
                    "既定のローカル接続文字列を使用します"
                    "（docker-compose.yml のPostgreSQL、または実際の接続先を設定してください）。"
                ),
            )
        )

    return warnings
