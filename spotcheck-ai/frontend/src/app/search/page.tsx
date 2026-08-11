"use client";

/**
 * 下部タブ「さがす」。地図から撮影依頼を探す。
 * 地名・住所での検索に対応し、検索した地点を中心に近くの依頼を再取得する。
 */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { PlaceSearchBox, type SearchedPlace } from "@/components/map/PlaceSearchBox";
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

/** 検索範囲の選択肢（km）。バックエンドの許容範囲は 0.5〜50km。 */
const RADIUS_OPTIONS = [1, 3, 5, 10, 30];

export default function SearchPage() {
  const toast = useToast();
  const [center, setCenter] = useState(env.defaultMapCenter);
  const [address, setAddress] = useState<string | null>(null);
  const [radiusKm, setRadiusKm] = useState(5);
  const [tasks, setTasks] = useState<NearbyTask[] | null>(null);
  const [selected, setSelected] = useState<NearbyTask | null>(null);

  // 初期表示は現在地。拒否された場合は既定座標のまま。
  useEffect(() => {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
      (position) => setCenter({ lat: position.coords.latitude, lng: position.coords.longitude }),
      () => undefined,
      { enableHighAccuracy: true, timeout: 8000 },
    );
  }, []);

  const load = useCallback(async () => {
    try {
      const { tasks: fetched } = await listNearbyTasks({ ...center, radiusKm });
      setTasks(fetched);
      setSelected(null);
    } catch (cause) {
      setTasks([]);
      toast.error(toMessage(cause));
    }
  }, [center, radiusKm, toast]);

  useEffect(() => {
    void load();
  }, [load]);

  const search = (place: SearchedPlace) => {
    setCenter({ lat: place.lat, lng: place.lng });
    setAddress(place.address);
  };

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold text-slate-800">さがす</h1>

      <PlaceSearchBox onSelect={search} accent="worker" />

      <div className="flex items-center justify-between gap-3">
        <p className="min-w-0 flex-1 truncate text-xs text-slate-500">
          {address ?? "現在地の周辺"}
        </p>
        <label className="flex items-center gap-1 text-xs text-slate-500">
          範囲
          <select
            value={radiusKm}
            onChange={(e) => setRadiusKm(Number(e.target.value))}
            className="rounded-lg border border-slate-300 px-2 py-1.5 text-xs"
            aria-label="検索範囲"
          >
            {RADIUS_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}km
              </option>
            ))}
          </select>
        </label>
      </div>

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
            href={`/jobs/${selected.id}`}
            className="block rounded-lg bg-worker py-2.5 text-center text-xs font-bold text-white"
          >
            詳細を見る
          </Link>
        </Card>
      )}

      <div className="space-y-3">
        <p className="text-xs text-slate-500">この範囲の依頼 {tasks?.length ?? 0}件</p>
        {tasks === null && <Skeleton className="h-28" />}
        {tasks?.length === 0 && (
          <EmptyState message="この範囲に募集中の依頼がありません。範囲を広げるか、別の地点で検索してください。" />
        )}
        <ul className="space-y-3">
          {tasks?.map((task) => (
            <TaskCard key={task.id} task={task} />
          ))}
        </ul>
      </div>
    </div>
  );
}
