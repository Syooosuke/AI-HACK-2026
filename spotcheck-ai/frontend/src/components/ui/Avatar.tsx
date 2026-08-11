"use client";

/**
 * 丸型のプロフィールアイコン。
 *
 * - 画像が未設定・読み込み失敗のときは、表示名の頭文字を丸で描く
 *   （外部素材に依存せず、誰でも必ず何かが表示される状態にする）
 * - 背景色は表示名から決めるため、同じ人はいつも同じ色になる
 */

import { useEffect, useState } from "react";

import { resolveApiUrl } from "@/lib/api/client";

const SIZE_CLASS = {
  xs: "h-7 w-7 text-[11px]",
  sm: "h-9 w-9 text-xs",
  md: "h-12 w-12 text-base",
  lg: "h-16 w-16 text-xl",
  xl: "h-24 w-24 text-3xl",
} as const;

export type AvatarSize = keyof typeof SIZE_CLASS;

/** 頭文字の背景色。彩度を抑えて、文字（白）が読める濃さに揃える。 */
const FALLBACK_COLORS = ["#2563EB", "#059669", "#7C3AED", "#D97706", "#DB2777", "#0891B2"];

function colorOf(name: string): string {
  const seed = Array.from(name).reduce((total, char) => total + char.charCodeAt(0), 0);
  return FALLBACK_COLORS[seed % FALLBACK_COLORS.length];
}

/** 表示名の頭文字（サロゲートペアの絵文字でも壊れないように取り出す）。 */
function initialOf(name: string): string {
  return Array.from(name.trim())[0] ?? "?";
}

export function Avatar({
  name,
  src,
  size = "md",
  className = "",
}: {
  name: string;
  /** APIが返すアバターURL（相対パス）。未設定なら null。 */
  src?: string | null;
  size?: AvatarSize;
  className?: string;
}) {
  const [failed, setFailed] = useState(false);

  // 画像を差し替えた直後は URL が変わるので、失敗状態を持ち越さない
  useEffect(() => setFailed(false), [src]);

  const shape = `inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full bg-slate-100 ${SIZE_CLASS[size]} ${className}`;

  if (!src || failed) {
    return (
      <span
        className={`${shape} font-bold text-white`}
        style={{ backgroundColor: colorOf(name) }}
        role="img"
        aria-label={`${name}のアイコン`}
      >
        {initialOf(name)}
      </span>
    );
  }

  return (
    <span className={shape}>
      {/* eslint-disable-next-line @next/next/no-img-element -- バックエンド配信のため next/image の最適化は使わない */}
      <img
        src={resolveApiUrl(src)}
        alt={`${name}のアイコン`}
        className="h-full w-full object-cover"
        onError={() => setFailed(true)}
      />
    </span>
  );
}
