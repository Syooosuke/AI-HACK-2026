import { apiFetch } from "@/lib/api/client";
import type { DemoUser } from "@/types/api";

/** `GET /api/users/demo`。認証前に呼ぶためデモユーザーヘッダーは付けない。 */
export function listDemoUsers(): Promise<{ users: DemoUser[] }> {
  return apiFetch<{ users: DemoUser[] }>("/api/users/demo", { demoUserId: null });
}
