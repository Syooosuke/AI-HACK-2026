import { apiFetch } from "@/lib/api/client";
import type { DemoUser, PublicProfile } from "@/types/api";

/** `GET /api/users/demo`。認証前に呼ぶためデモユーザーヘッダーは付けない。 */
export function listDemoUsers(): Promise<{ users: DemoUser[] }> {
  return apiFetch<{ users: DemoUser[] }>("/api/users/demo", { demoUserId: null });
}

/** `GET /api/users/{userId}/public`。閲覧専用の公開プロフィール。 */
export function getPublicProfile(userId: string): Promise<PublicProfile> {
  return apiFetch<PublicProfile>(`/api/users/${userId}/public`);
}
