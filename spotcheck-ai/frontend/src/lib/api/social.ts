/** いいね・保存した検索条件（ハート欄）のAPI。 */

import { apiFetch } from "@/lib/api/client";
import type { LikeResult, NearbyTask, SavedSearch } from "@/types/api";

export function likeTask(taskId: string): Promise<LikeResult> {
  return apiFetch<LikeResult>(`/api/tasks/${taskId}/like`, { method: "POST" });
}

export function unlikeTask(taskId: string): Promise<LikeResult> {
  return apiFetch<LikeResult>(`/api/tasks/${taskId}/like`, { method: "DELETE" });
}

/** いいねした投稿（新しい順）。 */
export function listLikedTasks(): Promise<{ tasks: NearbyTask[] }> {
  return apiFetch<{ tasks: NearbyTask[] }>("/api/likes");
}

export function listSavedSearches(): Promise<{ searches: SavedSearch[] }> {
  return apiFetch<{ searches: SavedSearch[] }>("/api/saved-searches");
}

export type SaveSearchInput = {
  label?: string;
  centerLat: number;
  centerLng: number;
  locationAddress?: string | null;
  radiusKm: number;
  sort?: "distance" | "reward" | "deadline";
};

export function saveSearch(input: SaveSearchInput): Promise<{ search: SavedSearch }> {
  return apiFetch<{ search: SavedSearch }>("/api/saved-searches", {
    method: "POST",
    body: { ...input },
  });
}

export function deleteSavedSearch(searchId: string): Promise<void> {
  return apiFetch<void>(`/api/saved-searches/${searchId}`, { method: "DELETE" });
}
