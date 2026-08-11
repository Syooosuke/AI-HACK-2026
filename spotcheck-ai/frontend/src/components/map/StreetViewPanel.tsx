"use client";

/**
 * 指定地点のストリートビュー。「どこにピンを置けばよいか」を実景で確かめるために使う。
 *
 * - `position` が変わるたびに、その近くのパノラマを探して表示する
 * - ストリートビュー内を歩いて移動できる。移動した先を撮影地点にしたい場合は
 *   `onAdopt` を呼び出す（親がピンを動かす）
 * - パノラマが無い地点・APIが使えない場合は理由を出して静かに畳む
 *   （ストリートビューは Maps JavaScript API の一部だが、課金が有効でないと使えない）
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { useGoogleMaps } from "@/components/map/useGoogleMaps";
import type { GStreetViewPanorama, LatLngLiteral } from "@/types/google-maps";

type PanoramaState = "idle" | "searching" | "ready" | "unavailable" | "error";

/** パノラマを探す半径（m）。指定地点にピンポイントで無くても近くの道路上を拾う。 */
const SEARCH_RADIUS_METERS = 80;

export function StreetViewPanel({
  position,
  onAdopt,
  className = "",
}: {
  position: LatLngLiteral;
  /** ストリートビューで移動した位置を撮影地点として採用する。 */
  onAdopt?: (position: LatLngLiteral) => void;
  className?: string;
}) {
  const status = useGoogleMaps();
  const containerRef = useRef<HTMLDivElement>(null);
  const panoramaRef = useRef<GStreetViewPanorama | null>(null);
  const [state, setState] = useState<PanoramaState>("idle");
  /** ストリートビュー内で移動した現在位置（採用ボタンで使う）。 */
  const [viewPosition, setViewPosition] = useState<LatLngLiteral | null>(null);

  const showPanorama = useCallback((target: LatLngLiteral) => {
    const maps = window.google?.maps;
    if (!maps || !containerRef.current) return;

    setState("searching");
    new maps.StreetViewService().getPanorama(
      { location: target, radius: SEARCH_RADIUS_METERS },
      (data, panoramaStatus) => {
        const found = data?.location?.latLng;
        if (panoramaStatus !== maps.StreetViewStatus.OK || !found) {
          setState(panoramaStatus === maps.StreetViewStatus.ZERO_RESULTS ? "unavailable" : "error");
          panoramaRef.current?.setVisible(false);
          return;
        }

        const panoPosition = { lat: found.lat(), lng: found.lng() };
        if (!panoramaRef.current) {
          panoramaRef.current = new maps.StreetViewPanorama(containerRef.current!, {
            position: panoPosition,
            pov: { heading: 0, pitch: 0 },
            addressControl: false,
            fullscreenControl: false,
            motionTracking: false,
            motionTrackingControl: false,
          });
          panoramaRef.current.addListener("position_changed", () => {
            const current = panoramaRef.current?.getPosition();
            if (current) setViewPosition({ lat: current.lat(), lng: current.lng() });
          });
        } else {
          panoramaRef.current.setPosition(panoPosition);
          panoramaRef.current.setVisible(true);
        }
        setViewPosition(panoPosition);
        setState("ready");
      },
    );
  }, []);

  useEffect(() => {
    if (status !== "ready") return;
    showPanorama(position);
  }, [status, position, showPanorama]);

  if (status === "unavailable" || status === "error") {
    // 地図自体が使えない場合はこのパネルを出さない（同じ警告を二重に出さない）
    return null;
  }

  return (
    <div className={`space-y-2 ${className}`}>
      <div className="relative overflow-hidden rounded-xl bg-slate-200">
        <div
          ref={containerRef}
          className={`h-56 w-full md:h-72 ${state === "ready" ? "" : "invisible"}`}
        />
        {state !== "ready" && (
          <div className="absolute inset-0 flex items-center justify-center px-6 text-center text-xs text-slate-500">
            {state === "searching" || state === "idle"
              ? "ストリートビューを探しています…"
              : state === "unavailable"
                ? "この地点のストリートビューはありません。地図でピンを動かすか、別の場所で試してください。"
                : "ストリートビューを表示できませんでした（Google Cloud で課金の有効化が必要な場合があります）。"}
          </div>
        )}
      </div>

      {state === "ready" && (
        <div className="flex items-center justify-between gap-2">
          <p className="text-xs text-slate-500">
            画面をドラッグして周囲を確認できます。矢印で移動もできます。
          </p>
          {onAdopt && viewPosition && (
            <button
              type="button"
              onClick={() => onAdopt(viewPosition)}
              className="shrink-0 rounded-lg border border-client px-3 py-1.5 text-xs font-bold text-client hover:bg-blue-50"
            >
              この位置を撮影地点にする
            </button>
          )}
        </div>
      )}
    </div>
  );
}
