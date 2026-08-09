/**
 * デモユーザーの保持と切替（D-06 / docs/05-frontend.md 2節）。
 * 選択したIDを localStorage に保持し、APIクライアントが全リクエストへ自動付与する。
 */

import type { DemoUser } from "@/types/api";

const STORAGE_KEY = "spotcheck.demoUser";
const CHANGE_EVENT = "spotcheck:demoUserChanged";

export function getDemoUser(): DemoUser | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as DemoUser;
  } catch {
    window.localStorage.removeItem(STORAGE_KEY);
    return null;
  }
}

export function getDemoUserId(): string | null {
  return getDemoUser()?.id ?? null;
}

export function setDemoUser(user: DemoUser): void {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(user));
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

export function clearDemoUser(): void {
  window.localStorage.removeItem(STORAGE_KEY);
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

/** 現在のデモユーザーの変更を購読する（ヘッダー表示の更新に使う）。 */
export function subscribeDemoUser(listener: () => void): () => void {
  window.addEventListener(CHANGE_EVENT, listener);
  window.addEventListener("storage", listener);
  return () => {
    window.removeEventListener(CHANGE_EVENT, listener);
    window.removeEventListener("storage", listener);
  };
}
