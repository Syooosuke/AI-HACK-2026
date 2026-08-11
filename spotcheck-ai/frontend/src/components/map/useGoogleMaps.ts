"use client";

/**
 * Google Maps JavaScript API のローダー。
 * キーが未設定のときは `unavailable` を返し、呼び出し側はフォールバックUIを出す
 * （docs/01-architecture.md 4節）。
 */

import { useEffect, useState } from "react";

import { env } from "@/lib/env";

export type MapsStatus = "unavailable" | "loading" | "ready" | "error";

function loadScript(apiKey: string): Promise<void> {
  if (window.google?.maps) return Promise.resolve();
  if (window.__spotcheckMapsLoader) return window.__spotcheckMapsLoader;

  window.__spotcheckMapsLoader = new Promise<void>((resolve, reject) => {
    const script = document.createElement("script");
    // places: 地名・住所での検索に使う。Places API が無効なキーでも地図自体は動く
    script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(apiKey)}&language=ja&region=JP&libraries=places`;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Google Maps の読み込みに失敗しました"));
    document.head.appendChild(script);
  });
  return window.__spotcheckMapsLoader;
}

export function useGoogleMaps(): MapsStatus {
  const [status, setStatus] = useState<MapsStatus>(
    env.googleMapsApiKey ? "loading" : "unavailable",
  );

  useEffect(() => {
    if (!env.googleMapsApiKey) {
      setStatus("unavailable");
      return;
    }
    let cancelled = false;
    loadScript(env.googleMapsApiKey)
      .then(() => {
        if (!cancelled) setStatus(window.google?.maps ? "ready" : "error");
      })
      .catch(() => {
        if (!cancelled) setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return status;
}
