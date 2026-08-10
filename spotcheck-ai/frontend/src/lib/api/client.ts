/**
 * バックエンドAPIの唯一の入口。
 * コンポーネントから `fetch` を直接書かず、必ずこの関数を経由する（CLAUDE.md 5節）。
 */

import { getDemoUserId } from "@/lib/demoUser";
import { env } from "@/lib/env";

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
  /** 明示的に上書きしたい場合のみ指定する。既定は localStorage のデモユーザー（D-06）。 */
  demoUserId?: string | null;
};

/** APIが返す相対的な画像URLを、バックエンドを指す絶対URLへ変換する。 */
export function resolveApiUrl(url: string): string {
  return new URL(url, `${env.apiBaseUrl.replace(/\/$/, "")}/`).toString();
}

export async function apiFetch<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const { body, demoUserId, headers, ...rest } = options;
  const requestHeaders = new Headers(headers);

  let requestBody: BodyInit | null | undefined;
  if (body instanceof FormData || typeof body === "string" || body == null) {
    // multipart は Content-Type を自動設定させる（boundary が必要なため）
    requestBody = body ?? null;
  } else {
    requestHeaders.set("Content-Type", "application/json");
    requestBody = JSON.stringify(body);
  }

  const userId = demoUserId !== undefined ? demoUserId : getDemoUserId();
  if (userId) {
    requestHeaders.set("X-Demo-User-Id", userId);
  }

  let response: Response;
  try {
    response = await fetch(`${env.apiBaseUrl}${path}`, {
      ...rest,
      headers: requestHeaders,
      body: requestBody,
      cache: rest.cache ?? "no-store",
    });
  } catch (cause) {
    throw new ApiError(
      0,
      "NETWORK_ERROR",
      "バックエンドに接続できません。サーバーが起動しているか確認してください。",
      { cause: String(cause) },
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const payload: unknown = await response.json().catch(() => null);

  if (!response.ok) {
    const errorBody = payload as ApiErrorBody | null;
    throw new ApiError(
      response.status,
      errorBody?.error?.code ?? "HTTP_ERROR",
      errorBody?.error?.message ?? "通信に失敗しました。",
      errorBody?.error?.details ?? {},
    );
  }

  return payload as T;
}
