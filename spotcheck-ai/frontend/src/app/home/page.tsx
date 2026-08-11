"use client";

/**
 * ホーム（ログイン直後の着地点）。近くの撮影依頼を一覧する。
 * 地図から探す場合は下部タブの「さがす」へ、依頼を出す場合は「依頼する」へ。
 */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { TaskCard } from "@/components/task/TaskCard";
import { Card, EmptyState, Skeleton } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";
import { toMessage } from "@/lib/api/errorMessages";
import { listNearbyTasks } from "@/lib/api/tasks";
import { env } from "@/lib/env";
import type { NearbyTask } from "@/types/api";

type SortKey = "distance" | "reward" | "deadline";

export default function HomePage() {
  const toast = useToast();
  const [sort, setSort] = useState<SortKey>("distance");
  const [center, setCenter] = useState(env.defaultMapCenter);
  const [geoDenied, setGeoDenied] = useState(false);
  const [tasks, setTasks] = useState<NearbyTask[] | null>(null);

  // 起動時に現在地を取得する。拒否された場合は既定座標にフォールバックする。
  useEffect(() => {
    if (!navigator.geolocation) {
      setGeoDenied(true);
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) => setCenter({ lat: position.coords.latitude, lng: position.coords.longitude }),
      () => setGeoDenied(true),
      { enableHighAccuracy: true, timeout: 8000 },
    );
  }, []);

  const load = useCallback(async () => {
    try {
      const { tasks: fetched } = await listNearbyTasks({ ...center, sort });
      setTasks(fetched);
    } catch (cause) {
      setTasks([]);
      toast.error(toMessage(cause));
    }
  }, [center, sort, toast]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-slate-800">近くの撮影依頼</h1>
        <Link href="/search" className="text-xs font-bold text-worker underline">
          地図でさがす
        </Link>
      </div>

      {geoDenied && (
        <Card className="border-amber-200 bg-amber-50">
          <p className="text-xs text-amber-800">
            現在地を取得できませんでした。既定の座標（渋谷駅周辺）で検索しています。
          </p>
        </Card>
      )}

      <div className="flex items-center justify-between">
        <p className="text-xs text-slate-500">{tasks?.length ?? 0}件</p>
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value as SortKey)}
          className="rounded-lg border border-slate-300 px-2 py-1.5 text-xs"
          aria-label="並び順"
        >
          <option value="distance">距離順</option>
          <option value="reward">報酬順</option>
          <option value="deadline">期限順</option>
        </select>
      </div>

      {tasks === null && (
        <div className="space-y-3">
          <Skeleton className="h-28" />
          <Skeleton className="h-28" />
        </div>
      )}
      {tasks?.length === 0 && (
        <EmptyState message="近くに募集中の依頼がありません。「さがす」で範囲を変えるか、「依頼する」から撮影を依頼できます。" />
      )}
      <ul className="space-y-3">
        {tasks?.map((task) => (
          <TaskCard key={task.id} task={task} />
        ))}
      </ul>
    </div>
  );
}
