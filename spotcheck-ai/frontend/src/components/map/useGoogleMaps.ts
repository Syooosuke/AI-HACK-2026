"use client";

/**
 * Google Maps JavaScript API のローダー。
 *
 * キーが未設定のときは `unavailable`、読み込み失敗やキーの認証失敗は `error` を返し、
 * 呼び出し側はフォールバックUIを出す（docs/01-architecture.md 4節）。
 *
 * キーが不正・課金未有効・リファラー制限違反の場合、スクリプト自体は読み込めるため
 * `onerror` では検知できない。Google が呼ぶ `window.gm_authFailure` を受け取って
 * `error` に落とし、**Googleの灰色オーバーレイではなく日本語の対処案内を出す。**
 */

import { useEffect, useState } from "react";

import { env } from "@/lib/env";

export type MapsStatus = "unavailable" | "loading" | "ready" | "error";

/** 認証失敗時に画面へ出す対処方法。原因を隠さず具体的に書く。 */
export const MAPS_AUTH_ERROR_MESSAGE =
  "地図の認証に失敗しました。Google Cloud で ①課金（Billing）の有効化 ②Maps JavaScript API の有効化 ③APIキーのリファラー制限に現在のURLが含まれているか を確認してください。";

let authFailed = false;
const authListeners = new Set<() => void>();

function markAuthFailure(): void {
  authFailed = true;
  authListeners.forEach((listener) => listener());
}

if (typeof window !== "undefined") {
  // Google Maps がキーの認証に失敗したときに呼ぶグローバル関数
  window.gm_authFailure = markAuthFailure;
}

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
    if (authFailed) {
      setStatus("error");
      return;
    }

    let cancelled = false;
    const onAuthFailure = () => {
      if (!cancelled) setStatus("error");
    };
    authListeners.add(onAuthFailure);

    loadScript(env.googleMapsApiKey)
      .then(() => {
        if (cancelled) return;
        setStatus(authFailed ? "error" : window.google?.maps ? "ready" : "error");
      })
      .catch(() => {
        if (!cancelled) setStatus("error");
      });

    return () => {
      cancelled = true;
      authListeners.delete(onAuthFailure);
    };
  }, []);

  return status;
}
