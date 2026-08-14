"use client";

/**
 * 下部タブ「いいね」。上から順に
 * 1. いいねした投稿
 * 2. 保存した検索条件
 * を並べる。保存した条件はタップするとその条件で地図を開く。
 */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { TaskCard } from "@/components/task/TaskCard";
import { EmptyState, SectionTitle, Skeleton } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";
import { toMessage } from "@/lib/api/errorMessages";
import { deleteSavedSearch, listLikedTasks, listSavedSearches } from "@/lib/api/social";
import { getPageCache, setPageCache } from "@/lib/pageCache";
import type { NearbyTask, SavedSearch } from "@/types/api";

const SORT_LABEL: Record<SavedSearch["sort"], string> = {
  distance: "距離順",
  reward: "報酬順",
  deadline: "期限順",
};

type LikesCache = { tasks: NearbyTask[]; searches: SavedSearch[] };
const LIKES_CACHE_KEY = "likes";

export default function LikesPage() {
  const toast = useToast();
  const cached = getPageCache<LikesCache>(LIKES_CACHE_KEY);
  const [tasks, setTasks] = useState<NearbyTask[] | null>(() => cached?.tasks ?? null);
  const [searches, setSearches] = useState<SavedSearch[] | null>(() => cached?.searches ?? null);

  const load = useCallback(async () => {
    try {
      const [liked, saved] = await Promise.all([listLikedTasks(), listSavedSearches()]);
      setTasks(liked.tasks);
      setSearches(saved.searches);
    } catch (cause) {
      setTasks([]);
      setSearches([]);
      toast.error(toMessage(cause));
    }
  }, [toast]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (tasks && searches) setPageCache<LikesCache>(LIKES_CACHE_KEY, { tasks, searches });
  }, [searches, tasks]);

  /** いいねを外した投稿はこの一覧から消す。 */
  const handleLikeChange = (taskId: string, liked: boolean) => {
    if (!liked) {
      setTasks((current) => current?.filter((task) => task.id !== taskId) ?? null);
    }
  };

  const removeSearch = async (search: SavedSearch) => {
    try {
      await deleteSavedSearch(search.id);
      setSearches((current) => current?.filter((item) => item.id !== search.id) ?? null);
    } catch (cause) {
      toast.error(toMessage(cause));
    }
  };

  return (
    <div className="space-y-6">
      <section className="space-y-3">
        <SectionTitle>いいねした投稿</SectionTitle>
        {tasks === null ? (
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 md:gap-4 lg:grid-cols-4">
            <Skeleton className="aspect-square" />
            <Skeleton className="aspect-square" />
          </div>
        ) : tasks.length === 0 ? (
          <EmptyState message="いいねした投稿はまだありません。ホームで気になる依頼のハートをタップすると、ここに集まります。" />
        ) : (
          <ul className="grid grid-cols-2 gap-3 md:grid-cols-3 md:gap-4 lg:grid-cols-4">
            {tasks.map((task) => (
              <TaskCard
                key={task.id}
                task={task}
                onLikeChange={handleLikeChange}
                onError={(message) => toast.error(message)}
              />
            ))}
          </ul>
        )}
      </section>

      <section className="space-y-3">
        <SectionTitle>保存した検索条件</SectionTitle>
        {searches === null ? (
          <Skeleton className="h-20" />
        ) : searches.length === 0 ? (
          <EmptyState message="保存した検索条件はまだありません。ホームで場所と範囲を決めて「条件を保存」を押すと、ここから呼び出せます。" />
        ) : (
          <ul className="space-y-2">
            {searches.map((search) => (
              <li
                key={search.id}
                className="flex items-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-sm"
              >
                <Link
                  href={`/search?lat=${search.centerLat}&lng=${search.centerLng}&radiusKm=${search.radiusKm}&sort=${search.sort}`}
                  className="min-w-0 flex-1"
                >
                  <span className="block truncate text-sm font-bold text-slate-800">
                    {search.label}
                  </span>
                  <span className="block text-xs text-slate-500">
                    {SORT_LABEL[search.sort]}
                    {search.lastMatchCount != null && ` ・ 現在 ${search.lastMatchCount}件`}
                  </span>
                </Link>
                <button
                  type="button"
                  onClick={() => void removeSearch(search)}
                  aria-label={`${search.label} を削除`}
                  className="rounded-lg px-2 py-1 text-xs font-bold text-slate-400 hover:bg-slate-100"
                >
                  削除
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
