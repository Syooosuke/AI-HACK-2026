/**
 * サービスロゴ（ワードマーク）。
 *
 * サービス名は **SpotCheck**。「AI」は名前に含めない。
 * 画像は `public/logo-wordmark.png`（元データから余白を落として書き出したもの）。
 */

import Image from "next/image";

/** 元画像の縦横比。高さから幅を決めるために使う。 */
const ASPECT = 398 / 96;

export function Logo({ height = 24, className = "" }: { height?: number; className?: string }) {
  return (
    <Image
      src="/logo-wordmark.png"
      alt="SpotCheck"
      width={Math.round(height * ASPECT)}
      height={height}
      priority
      className={className}
      style={{ height, width: "auto" }}
    />
  );
}
