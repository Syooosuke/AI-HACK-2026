"use client";

/**
 * 地図から撮影依頼を探す画面。ホームの「地図で見る」と、保存した検索条件から開く。
 * 地名・住所の検索に対応し、検索した地点を中心に近くの依頼を取り直す。
 */

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { PlaceSearchBox, type SearchedPlace } from "@/components/map/PlaceSearchBox";
import { TaskMarkers } from "@/components/map/TaskMarkers";
import { TaskCard } from "@/components/task/TaskCard";
import { Card, EmptyState, Skeleton } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";
import { toMessage } from "@/lib/api/errorMessages";
import { saveSearch } from "@/lib/api/social";
import { listNearbyTasks } from "@/lib/api/tasks";
import { formatRemaining } from "@/lib/datetime";
import { env } from "@/lib/env";
import { formatDistance } from "@/lib/geo";
import type { NearbyTask } from "@/types/api";

type SortKey = "distance" | "reward" | "deadline";

const RADIUS_OPTIONS = [1, 3, 5, 10, 30];

function parseNumber(value: string | null, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) && value !== null && value !== "" ? parsed : fallback;
}

export default function SearchPage() {
  const toast = useToast();
  const params = useSearchParams();

  // 保存した検索条件やホームから渡された地点・範囲を初期値にする
  const [center, setCenter] = useState({
    lat: parseNumber(params.get("lat"), env.defaultMapCenter.lat),
    lng: parseNumber(params.get("lng"), env.defaultMapCenter.lng),
  });
  const [radiusKm, setRadiusKm] = useState(parseNumber(params.get("radiusKm"), 5));
  const [sort, setSort] = useState<SortKey>((params.get("sort") as SortKey | null) ?? "distance");
  const [address, setAddress] = useState<string | null>(null);
  const [tasks, setTasks] = useState<NearbyTask[] | null>(null);
  const [selected, setSelected] = useState<NearbyTask | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const { tasks: fetched } = await listNearbyTasks({ ...center, radiusKm, sort });
      setTasks(fetched);
      setSelected(null);
    } catch (cause) {
      setTasks([]);
      toast.error(toMessage(cause));
    }
  }, [center, radiusKm, sort, toast]);

  useEffect(() => {
    void load();
  }, [load]);

  const search = (place: SearchedPlace) => {
    setCenter({ lat: place.lat, lng: place.lng });
    setAddress(place.address);
  };

  const save = async () => {
    setSaving(true);
    try {
      const { search: saved } = await saveSearch({
        centerLat: center.lat,
        centerLng: center.lng,
        locationAddress: address,
        radiusKm,
        sort,
      });
      toast.success(`「${saved.label}」を保存しました`);
    } catch (cause) {
      toast.error(toMessage(cause));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold text-slate-800">地図でさがす</h1>

      <PlaceSearchBox onSelect={search} accent="worker" />

      <div className="flex items-center gap-2">
        <p className="min-w-0 flex-1 truncate text-xs text-slate-500">
          {address ?? "現在の中心地点"}
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
        <label className="flex items-center gap-1 text-xs text-slate-500">
          並び
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
        </label>
        <button
          type="button"
          onClick={() => void save()}
          disabled={saving}
          className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-bold text-slate-600 hover:bg-slate-50 disabled:opacity-50"
        >
          ♡ 保存
        </button>
      </div>

      <TaskMarkers center={center} tasks={tasks ?? []} onSelect={setSelected} />

      {selected && (
        <Card className="space-y-2 border-worker">
          <p className="text-sm font-bold text-slate-800">{selected.title}</p>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
            <span>💰 ¥{selected.rewardAmount.toLocaleString()}</span>
            {selected.distanceKm != null && <span>📍 {formatDistance(selected.distanceKm)}</span>}
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
        {tasks === null && (
          <div className="grid grid-cols-2 gap-3">
            <Skeleton className="aspect-square" />
            <Skeleton className="aspect-square" />
          </div>
        )}
        {tasks?.length === 0 && (
          <EmptyState message="この範囲に募集中の依頼がありません。範囲を広げるか、別の地点で検索してください。" />
        )}
        <ul className="grid grid-cols-2 gap-3">
          {tasks?.map((task) => (
            <TaskCard key={task.id} task={task} onError={(message) => toast.error(message)} />
          ))}
        </ul>
      </div>
    </div>
  );
}
