import { apiFetch } from "@/lib/api/client";
import type { PublicProfile } from "@/types/api";

/** `GET /api/users/{userId}/public`。閲覧専用の公開プロフィール（docs/03-api.md 3.4.1）。 */
export function getPublicProfile(userId: string): Promise<PublicProfile> {
  return apiFetch<PublicProfile>(`/api/users/${userId}/public`);
}
