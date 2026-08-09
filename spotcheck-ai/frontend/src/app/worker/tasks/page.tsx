"use client";

/** 画面④ 依頼一覧 / 地図（docs/05-frontend.md 画面④）。 */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { TaskMarkers } from "@/components/map/TaskMarkers";
import { TaskCard } from "@/components/task/TaskCard";
import { Card, EmptyState, Skeleton } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";
import { toMessage } from "@/lib/api/errorMessages";
import { listNearbyTasks } from "@/lib/api/tasks";
import { formatRemaining } from "@/lib/datetime";
import { env } from "@/lib/env";
import { formatDistance } from "@/lib/geo";
import type { NearbyTask } from "@/types/api";

type SortKey = "distance" | "reward" | "deadline";

export default function WorkerTasksPage() {
  const toast = useToast();
  const [tab, setTab] = useState<"map" | "list">("list");
  const [sort, setSort] = useState<SortKey>("distance");
  const [center, setCenter] = useState(env.defaultMapCenter);
  const [geoDenied, setGeoDenied] = useState(false);
  const [tasks, setTasks] = useState<NearbyTask[] | null>(null);
  const [selected, setSelected] = useState<NearbyTask | null>(null);

  // 起動時に現在地を取得する。拒否された場合は既定座標にフォールバックする。
  useEffect(() => {
    if (!navigator.geolocation) {
      setGeoDenied(true);
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) =>
        setCenter({ lat: position.coords.latitude, lng: position.coords.longitude }),
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
      <h1 className="text-lg font-bold text-slate-800">近くの依頼</h1>

      {geoDenied && (
        <Card className="border-amber-200 bg-amber-50">
          <p className="text-xs text-amber-800">
            現在地を取得できませんでした。既定の座標（渋谷駅周辺）で検索しています。
          </p>
        </Card>
      )}

      <div className="flex rounded-xl bg-slate-100 p-1">
        {(["map", "list"] as const).map((key) => (
          <button
            key={key}
            type="button"
            onClick={() => setTab(key)}
            className={`flex-1 rounded-lg py-2 text-sm font-bold transition ${
              tab === key ? "bg-white text-worker shadow-sm" : "text-slate-500"
            }`}
          >
            {key === "map" ? "地図" : "リスト"}
          </button>
        ))}
      </div>

      {tab === "map" ? (
        <div className="space-y-3">
          <TaskMarkers center={center} tasks={tasks ?? []} onSelect={setSelected} />
          {selected && (
            <Card className="space-y-2 border-worker">
              <p className="text-sm font-bold text-slate-800">{selected.title}</p>
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
                <span>💰 ¥{selected.rewardAmount.toLocaleString()}</span>
                <span>📍 {formatDistance(selected.distanceKm)}</span>
                <span>⏳ {formatRemaining(selected.deadlineAt)}</span>
              </div>
              <Link
                href={`/worker/tasks/${selected.id}`}
                className="block rounded-lg bg-worker py-2.5 text-center text-xs font-bold text-white"
              >
                詳細を見る
              </Link>
            </Card>
          )}
        </div>
      ) : (
        <>
          <div className="flex items-center justify-between">
            <p className="text-xs text-slate-500">{tasks?.length ?? 0}件</p>
            <select
              value={sort}
              onChange={(e) => setSort(e.target.value as SortKey)}
              className="rounded-lg border border-slate-300 px-2 py-1.5 text-xs"
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
            <EmptyState message="近くに募集中の依頼がありません。クライアントに切り替えて依頼を作成してみてください。" />
          )}
          <ul className="space-y-3">
            {tasks?.map((task) => (
              <TaskCard key={task.id} task={task} />
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
