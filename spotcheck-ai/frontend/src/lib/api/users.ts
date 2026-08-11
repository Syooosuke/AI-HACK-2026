/** ユーザーAPI（`/api/users/*`）。アバターの差し替えと公開プロフィールの取得。 */

import { apiFetch } from "@/lib/api/client";
import type { AuthUser, PublicProfile } from "@/types/api";

/** アバターを差し替える。更新後のユーザー情報を返す。 */
export function uploadAvatar(file: File): Promise<{ user: AuthUser }> {
  const form = new FormData();
  form.append("image", file);
  return apiFetch<{ user: AuthUser }>("/api/users/me/avatar", {
    method: "POST",
    body: form,
  });
}

/** アバターを削除して既定表示（頭文字の丸）へ戻す。 */
export function deleteAvatar(): Promise<{ user: AuthUser }> {
  return apiFetch<{ user: AuthUser }>("/api/users/me/avatar", { method: "DELETE" });
}

/** `GET /api/users/{userId}/public`。閲覧専用の公開プロフィール（docs/03-api.md 3.4.1）。 */
export function getPublicProfile(userId: string): Promise<PublicProfile> {
  return apiFetch<PublicProfile>(`/api/users/${userId}/public`);
}
