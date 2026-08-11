/**
 * ログインセッションの保持。
 * アクセストークンとユーザー情報を localStorage に置き、
 * `lib/api/client.ts` が全リクエストへ `Authorization: Bearer` を付与する。
 * ネイティブアプリのように、一度ログインすれば次回起動時もログイン状態が続く。
 */

import type { AuthUser } from "@/types/api";

const TOKEN_KEY = "spotcheck.token";
const USER_KEY = "spotcheck.user";
const CHANGE_EVENT = "spotcheck:sessionChanged";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function getCurrentUser(): AuthUser | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthUser;
  } catch {
    window.localStorage.removeItem(USER_KEY);
    return null;
  }
}

export function saveSession(token: string, user: AuthUser): void {
  window.localStorage.setItem(TOKEN_KEY, token);
  window.localStorage.setItem(USER_KEY, JSON.stringify(user));
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

/** ユーザー情報のみ更新する（信頼度スコアの再取得など）。 */
export function saveUser(user: AuthUser): void {
  window.localStorage.setItem(USER_KEY, JSON.stringify(user));
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

export function clearSession(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(USER_KEY);
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

/** セッションの変更を購読する（ヘッダー表示やガードの更新に使う）。 */
export function subscribeSession(listener: () => void): () => void {
  window.addEventListener(CHANGE_EVENT, listener);
  window.addEventListener("storage", listener);
  return () => {
    window.removeEventListener(CHANGE_EVENT, listener);
    window.removeEventListener("storage", listener);
  };
}
