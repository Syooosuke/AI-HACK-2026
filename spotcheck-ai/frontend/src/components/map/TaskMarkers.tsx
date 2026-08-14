"use client";

/**
 * 近傍タスクのマーカー表示（画面④の地図タブ）。
 * 現在地を青丸、タスクをピンで表示し、タップで下部カードを出す。
 * ピンの色は投稿カードのタグ（SOLD/HOT/NEW）と対応させる。
 * APIキー未設定時はリスト表示への案内にフォールバックする。
 */

import { useEffect, useRef } from "react";

import { MAPS_AUTH_ERROR_MESSAGE, useGoogleMaps } from "@/components/map/useGoogleMaps";
import type { GMap, GMarker } from "@/types/google-maps";
import type { NearbyTask, TaskBadge } from "@/types/api";

/**
 * ピンの形（SVGパス）。原点が先端で、そこから上へ膨らむ雫形。
 * `anchor` を (0,0) にすることで、先端がちょうど座標を指す。
 */
const PIN_PATH =
  "M 0 0 C -3 -6 -10 -10 -10 -17 a 10 10 0 1 1 20 0 C 10 -10 3 -6 0 0 z M 0 -17 m -4 0 a 4 4 0 1 0 8 0 a 4 4 0 1 0 -8 0";

/** タグの色（CornerBadge と同じ考え方: sold > hot > new）。 */
const BADGE_COLOR: Record<TaskBadge, string> = {
  sold: "#1E293B", // slate-800
  hot: "#EF4444", // fail
  new: "#059669", // worker
};

/** タグが無い依頼は、募集中を表す既定色（依頼の青）にする。 */
const DEFAULT_COLOR = "#2563EB";

function markerColor(badges: TaskBadge[]): string {
  // 並び順はサーバー側（task_card.py）で優先度順になっている
  const badge = badges[0];
  return badge ? BADGE_COLOR[badge] : DEFAULT_COLOR;
}

export function TaskMarkers({
  center,
  tasks,
  onSelect,
}: {
  center: { lat: number; lng: number };
  tasks: NearbyTask[];
  onSelect: (task: NearbyTask) => void;
}) {
  const status = useGoogleMaps();
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<GMap | null>(null);
  const markersRef = useRef<GMarker[]>([]);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  useEffect(() => {
    if (status !== "ready" || !containerRef.current) return;
    const maps = window.google!.maps;

    if (!mapRef.current) {
      mapRef.current = new maps.Map(containerRef.current, {
        center,
        zoom: 15,
        disableDefaultUI: true,
        zoomControl: true,
      });
      // 現在地（青丸）
      new maps.Marker({
        position: center,
        map: mapRef.current,
        title: "現在地",
        icon: {
          path: 0, // google.maps.SymbolPath.CIRCLE
          scale: 7,
          fillColor: "#2563EB",
          fillOpacity: 1,
          strokeColor: "#ffffff",
          strokeWeight: 2,
        },
      });
    } else {
      mapRef.current.setCenter(center);
    }

    markersRef.current.forEach((marker) => marker.setMap(null));
    markersRef.current = tasks.map((task) => {
      const marker = new maps.Marker({
        position: { lat: task.locationLat, lng: task.locationLng },
        map: mapRef.current!,
        title: task.title,
        // ピン形状にし、色はカードのタグ（SOLD/HOT/NEW）と揃える。
        // 一覧と地図で同じ依頼が同じ色になり、見比べられるようにするため
        icon: {
          path: PIN_PATH,
          fillColor: markerColor(task.badges),
          fillOpacity: 1,
          strokeColor: "#ffffff",
          strokeWeight: 1.5,
          scale: 1.6,
          // パスの原点は先端。先端が座標に刺さるようにする
          anchor: new maps.Point(0, 0),
        },
        // 取引終了は目立たせない（募集中の依頼を優先して見せる）
        zIndex: task.badges.includes("sold") ? 1 : 2,
      });
      marker.addListener("click", () => onSelectRef.current(task));
      return marker;
    });
  }, [status, center, tasks]);

  if (status !== "ready") {
    return (
      <div className="flex h-72 flex-col items-center justify-center gap-2 rounded-2xl bg-slate-100 px-6 text-center text-sm text-slate-500 md:h-96">
        {status === "loading" ? (
          "地図を読み込んでいます…"
        ) : (
          <>
            <p className="text-xs">
              {status === "error" ? MAPS_AUTH_ERROR_MESSAGE : "地図APIキーが未設定です。"}
            </p>
            <p className="text-xs">ホームのリストから依頼を確認できます。</p>
          </>
        )}
      </div>
    );
  }

  return <div ref={containerRef} className="h-72 w-full overflow-hidden rounded-2xl bg-slate-200 md:h-96" />;
}
