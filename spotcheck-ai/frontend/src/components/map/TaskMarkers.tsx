"use client";

/**
 * 近傍タスクのマーカー表示（画面④の地図タブ）。
 * 現在地を青丸、タスクを緑ピンで表示し、タップで下部カードを出す。
 * APIキー未設定時はリスト表示への案内にフォールバックする。
 */

import { useEffect, useRef } from "react";

import { useGoogleMaps } from "@/components/map/useGoogleMaps";
import type { GMap, GMarker } from "@/types/google-maps";
import type { NearbyTask } from "@/types/api";

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
        icon: {
          path: 0,
          scale: 9,
          fillColor: "#059669",
          fillOpacity: 1,
          strokeColor: "#ffffff",
          strokeWeight: 2,
        },
      });
      marker.addListener("click", () => onSelectRef.current(task));
      return marker;
    });
  }, [status, center, tasks]);

  if (status !== "ready") {
    return (
      <div className="flex h-72 flex-col items-center justify-center gap-2 rounded-2xl bg-slate-100 px-6 text-center text-sm text-slate-500">
        {status === "loading" ? (
          "地図を読み込んでいます…"
        ) : (
          <>
            <p>
              {status === "error"
                ? "地図を読み込めませんでした。"
                : "地図APIキーが未設定です。"}
            </p>
            <p className="text-xs">「リスト」タブから依頼を確認できます。</p>
          </>
        )}
      </div>
    );
  }

  return <div ref={containerRef} className="h-72 w-full overflow-hidden rounded-2xl bg-slate-200" />;
}
