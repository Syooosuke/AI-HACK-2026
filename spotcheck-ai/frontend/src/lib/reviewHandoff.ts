/**
 * 画面①→②の受け渡し。
 * 画面②は `POST /api/tasks` のレスポンスを表示する画面なので、直前の結果を sessionStorage で渡す。
 */

import type { TaskReviewResponse } from "@/types/api";

const KEY = "spotcheck.lastReview";

export function saveReview(review: TaskReviewResponse): void {
  window.sessionStorage.setItem(KEY, JSON.stringify(review));
}

export function loadReview(): TaskReviewResponse | null {
  if (typeof window === "undefined") return null;
  const raw = window.sessionStorage.getItem(KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as TaskReviewResponse;
  } catch {
    return null;
  }
}

export function clearReview(): void {
  window.sessionStorage.removeItem(KEY);
}
