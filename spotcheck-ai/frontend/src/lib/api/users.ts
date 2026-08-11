/** プロフィール（アバター画像）API（`/api/users/*`）。 */

import { apiFetch } from "@/lib/api/client";
import type { AuthUser } from "@/types/api";

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
