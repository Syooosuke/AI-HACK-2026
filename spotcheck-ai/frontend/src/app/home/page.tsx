"use client";

/**
 * ホーム（ログイン直後の着地点）。近くの撮影依頼を並べる。
 * 上部に地名・住所の検索を置き、検索した条件は「保存」してハート欄から呼び出せる。
 */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { PlaceSearchBox, type SearchedPlace } from "@/components/map/PlaceSearchBox";
import { TaskCard } from "@/components/task/TaskCard";
import { Card, EmptyState, Skeleton } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";
import { toMessage } from "@/lib/api/errorMessages";
import { saveSearch } from "@/lib/api/social";
import { listNearbyTasks } from "@/lib/api/tasks";
import { env } from "@/lib/env";
import type { NearbyTask } from "@/types/api";

type SortKey = "distance" | "reward" | "deadline";

/** 検索範囲の選択肢（km）。バックエンドの許容範囲は 0.5〜50km。 */
const RADIUS_OPTIONS = [1, 3, 5, 10, 30];

export default function HomePage() {
  const toast = useToast();
  const [sort, setSort] = useState<SortKey>("distance");
  const [radiusKm, setRadiusKm] = useState(5);
  const [center, setCenter] = useState(env.defaultMapCenter);
  const [address, setAddress] = useState<string | null>(null);
  const [geoDenied, setGeoDenied] = useState(false);
  const [tasks, setTasks] = useState<NearbyTask[] | null>(null);
  const [saving, setSaving] = useState(false);

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
      const { tasks: fetched } = await listNearbyTasks({ ...center, radiusKm, sort });
      setTasks(fetched);
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

  const mapHref = `/search?lat=${center.lat}&lng=${center.lng}&radiusKm=${radiusKm}`;

  return (
    <div className="space-y-4">
      <PlaceSearchBox onSelect={search} accent="worker" />

      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="min-w-0 flex-1 truncate text-xs text-slate-500">
          {address ?? (geoDenied ? "渋谷駅周辺（現在地を取得できませんでした）" : "現在地の周辺")}
        </p>
        <Link href={mapHref} className="text-xs font-bold text-worker underline">
          地図で見る
        </Link>
      </div>

      <div className="flex items-center gap-2">
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
          className="ml-auto rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-bold text-slate-600 hover:bg-slate-50 disabled:opacity-50"
        >
          ♡ 条件を保存
        </button>
      </div>

      {tasks === null ? (
        <div className="grid grid-cols-2 gap-3">
          <Skeleton className="aspect-square" />
          <Skeleton className="aspect-square" />
        </div>
      ) : tasks.length === 0 ? (
        <EmptyState message="この範囲に募集中の依頼がありません。範囲を広げるか、別の地名で検索してください。" />
      ) : (
        <>
          <p className="text-xs text-slate-500">{tasks.length}件</p>
          <ul className="grid grid-cols-2 gap-3">
            {tasks.map((task) => (
              <TaskCard key={task.id} task={task} onError={(message) => toast.error(message)} />
            ))}
          </ul>
        </>
      )}

      <Card className="border-dashed">
        <p className="text-xs text-slate-500">
          撮影を依頼したいときは下の「依頼する」から作成できます。保存した検索条件といいねした投稿は
          「いいね」タブにまとまります。
        </p>
      </Card>
    </div>
  );
}
