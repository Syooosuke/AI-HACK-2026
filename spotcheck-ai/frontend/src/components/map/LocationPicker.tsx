"use client";

/**
 * 地点ピッカー（依頼作成）。地名・住所での検索と、地図タップによるピン配置の両方に対応する。
 * APIキー未設定・読み込み失敗時は緯度経度の手入力フォームへフォールバックする。
 */

import { useEffect, useRef } from "react";

import { PlaceSearchBox, type SearchedPlace } from "@/components/map/PlaceSearchBox";
import { useGoogleMaps } from "@/components/map/useGoogleMaps";
import { env } from "@/lib/env";
import { formatCoords } from "@/lib/geo";
import type { GMap, GMarker } from "@/types/google-maps";

export type PickedLocation = {
  lat: number;
  lng: number;
  address: string | null;
};

/** 検索で地点を選んだときの拡大率（周辺が分かる程度に寄せる）。 */
const SEARCH_ZOOM = 17;

export function LocationPicker({
  value,
  onChange,
}: {
  value: PickedLocation;
  onChange: (next: PickedLocation) => void;
}) {
  const status = useGoogleMaps();
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<GMap | null>(null);
  const markerRef = useRef<GMarker | null>(null);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  useEffect(() => {
    if (status !== "ready" || !containerRef.current || mapRef.current) return;
    const maps = window.google!.maps;
    const center = { lat: value.lat, lng: value.lng };
    const map = new maps.Map(containerRef.current, {
      center,
      zoom: 16,
      disableDefaultUI: true,
      zoomControl: true,
      clickableIcons: false,
    });
    const marker = new maps.Marker({ position: center, map, title: "撮影地点" });
    const geocoder = new maps.Geocoder();

    map.addListener("click", (event) => {
      const latLng = event.latLng;
      if (!latLng) return;
      const next = { lat: latLng.lat(), lng: latLng.lng() };
      marker.setPosition(next);
      onChangeRef.current({ ...next, address: null });
      // 逆ジオコーディングで住所を補完する（失敗しても座標だけで進める）
      geocoder.geocode({ location: next, language: "ja" }, (results, geocodeStatus) => {
        if (geocodeStatus === "OK" && results?.[0]) {
          onChangeRef.current({ ...next, address: results[0].formatted_address });
        }
      });
    });

    mapRef.current = map;
    markerRef.current = marker;
  }, [status, value.lat, value.lng]);

  /** 検索結果の地点へ地図とピンを移動する。 */
  const applySearch = (place: SearchedPlace) => {
    const position = { lat: place.lat, lng: place.lng };
    mapRef.current?.setCenter(position);
    mapRef.current?.setZoom(SEARCH_ZOOM);
    markerRef.current?.setPosition(position);
    onChangeRef.current({ ...position, address: place.address });
  };

  if (status === "ready") {
    return (
      <div className="space-y-2">
        <PlaceSearchBox onSelect={applySearch} />
        <div ref={containerRef} className="h-56 w-full overflow-hidden rounded-xl bg-slate-200 md:h-72" />
        <p className="text-xs text-slate-500">
          検索するか、地図をタップしてピンを移動できます — {formatCoords(value.lat, value.lng)}
        </p>
        {value.address && <p className="text-xs text-slate-600">{value.address}</p>}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {status === "loading" ? (
        <div className="flex h-56 items-center justify-center rounded-xl bg-slate-100 text-sm text-slate-500 md:h-72">
          地図を読み込んでいます…
        </div>
      ) : (
        <div className="rounded-xl bg-amber-50 px-3 py-2.5 text-xs text-amber-800">
          {status === "error"
            ? "地図を読み込めませんでした。緯度経度を直接入力してください。"
            : "地図APIキーが未設定のため、緯度経度を直接入力してください。"}
          <span className="ml-1 font-mono">NEXT_PUBLIC_GOOGLE_MAPS_API_KEY</span>
        </div>
      )}
      <div className="grid grid-cols-2 gap-3">
        <label className="block">
          <span className="mb-1 block text-xs font-bold text-slate-500">緯度</span>
          <input
            type="number"
            step="0.00001"
            value={value.lat}
            onChange={(e) => onChange({ ...value, lat: Number(e.target.value) })}
            className="w-full rounded-xl border border-slate-300 px-3 py-2.5"
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs font-bold text-slate-500">経度</span>
          <input
            type="number"
            step="0.00001"
            value={value.lng}
            onChange={(e) => onChange({ ...value, lng: Number(e.target.value) })}
            className="w-full rounded-xl border border-slate-300 px-3 py-2.5"
          />
        </label>
      </div>
      <label className="block">
        <span className="mb-1 block text-xs font-bold text-slate-500">住所（任意）</span>
        <input
          type="text"
          value={value.address ?? ""}
          placeholder="東京都渋谷区道玄坂1丁目"
          onChange={(e) => onChange({ ...value, address: e.target.value || null })}
          className="w-full rounded-xl border border-slate-300 px-3 py-2.5"
        />
      </label>
      <button
        type="button"
        onClick={() =>
          onChange({
            lat: env.defaultMapCenter.lat,
            lng: env.defaultMapCenter.lng,
            address: value.address,
          })
        }
        className="text-xs font-bold text-client underline"
      >
        既定の座標（渋谷駅周辺）に戻す
      </button>
    </div>
  );
}
