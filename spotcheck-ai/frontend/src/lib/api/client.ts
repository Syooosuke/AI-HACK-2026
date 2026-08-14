/**
 * バックエンドAPIの唯一の入口。
 * コンポーネントから `fetch` を直接書かず、必ずこの関数を経由する（CLAUDE.md 5節）。
 */

import { env } from "@/lib/env";
import { clearSession, getToken } from "@/lib/session";

/** docs/03-api.md 1.2 のエラーレスポンス形式。 */
export type ApiErrorBody = {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
};

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;

  constructor(status: number, code: string, message: string, details: Record<string, unknown> = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export type ApiFetchOptions = Omit<RequestInit, "body"> & {
  body?: BodyInit | Record<string, unknown> | null;
  /** 認証不要のエンドポイント（ログイン・新規登録）では false にする。 */
  auth?: boolean;
};

/** APIが返す相対的な画像URLを、バックエンドを指す絶対URLへ変換する。 */
export function resolveApiUrl(url: string): string {
  return new URL(url, `${env.apiBaseUrl.replace(/\/$/, "")}/`).toString();
}

/**
 * 読み取り系のリクエストだけ、一時的な失敗を1度だけ再試行する。
 *
 * 「サーバーに接続できません」が頻繁に出ていた理由は主に次の2つ。
 * 1. Cloud Run は無アクセスが続くとインスタンスを落とすため、久しぶりの1回目が
 *    立ち上がりに間に合わず落ちることがある
 * 2. モバイル回線の一瞬の切断。10秒ごとのポーリングがあるため、確率的に必ず当たる
 *
 * どちらも**すぐ再試行すれば通る**。書き込み（POST/DELETE）は再試行しない。
 * 二重に依頼が作られる・二重に受注されるといった実害が出るため。
 */
const RETRY_DELAY_MS = 600;
const RETRYABLE_METHODS = new Set(["GET", "HEAD"]);

async function fetchWithRetry(url: string, init: RequestInit, method: string): Promise<Response> {
  try {
    return await fetch(url, init);
  } catch (cause) {
    if (!RETRYABLE_METHODS.has(method)) {
      throw toNetworkError(cause);
    }
    await new Promise((resolve) => setTimeout(resolve, RETRY_DELAY_MS));
    try {
      return await fetch(url, init);
    } catch (retryCause) {
      throw toNetworkError(retryCause);
    }
  }
}

function toNetworkError(cause: unknown): ApiError {
  return new ApiError(
    0,
    "NETWORK_ERROR",
    "バックエンドに接続できません。サーバーが起動しているか確認してください。",
    { cause: String(cause) },
  );
}

export async function apiFetch<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const { body, auth = true, headers, ...rest } = options;
  const requestHeaders = new Headers(headers);

  let requestBody: BodyInit | null | undefined;
  if (body instanceof FormData || typeof body === "string" || body == null) {
    // multipart は Content-Type を自動設定させる（boundary が必要なため）
    requestBody = body ?? null;
  } else {
    requestHeaders.set("Content-Type", "application/json");
    requestBody = JSON.stringify(body);
  }

  if (auth) {
    const token = getToken();
    if (token) {
      requestHeaders.set("Authorization", `Bearer ${token}`);
    }
  }

  const method = (rest.method ?? "GET").toUpperCase();
  const response = await fetchWithRetry(
    `${env.apiBaseUrl}${path}`,
    {
      ...rest,
      headers: requestHeaders,
      body: requestBody,
      cache: rest.cache ?? "no-store",
    },
    method,
  );

  if (response.status === 204) {
    return undefined as T;
  }

  const payload: unknown = await response.json().catch(() => null);

  if (!response.ok) {
    const errorBody = payload as ApiErrorBody | null;
    if (response.status === 401 && auth) {
      // トークンが無効・期限切れになったらセッションを捨てる。
      // 画面側は AuthGuard がログイン画面へ戻す。
      clearSession();
    }
    throw new ApiError(
      response.status,
      errorBody?.error?.code ?? "HTTP_ERROR",
      errorBody?.error?.message ?? "通信に失敗しました。",
      errorBody?.error?.details ?? {},
    );
  }

  return payload as T;
}
