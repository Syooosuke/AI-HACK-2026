/**
 * 投稿の左上角に出すタグ。角を切り取る三角形の中に白文字を斜めに置く。
 *
 * 表示するのは**優先順位が最も高い1つだけ**（sold > hot > new）。
 * 並び順はサーバー側（`app/services/task_card.py`）で決めているため、
 * ここでは配列の先頭を採用する。
 */

import type { TaskBadge } from "@/types/api";

const BADGE: Record<TaskBadge, { label: string; borderClass: string }> = {
  // 取引終了。募集中の投稿より目立たせない濃いグレー
  sold: { label: "SOLD", borderClass: "border-t-slate-800" },
  // よく見られている
  hot: { label: "HOT", borderClass: "border-t-fail" },
  // 新着
  new: { label: "NEW", borderClass: "border-t-worker" },
};

export function CornerBadge({
  badges,
  size = "md",
}: {
  badges: TaskBadge[];
  /** md: 一覧のカード / lg: 詳細画面の大きな画像 */
  size?: "md" | "lg";
}) {
  const badge = badges[0];
  if (!badge) return null;

  const { label, borderClass } = BADGE[badge];
  const large = size === "lg";
  const box = large ? "h-24 w-24" : "h-16 w-16";
  // 三角形は border で作る（top を塗り、right を透明にすると左上の直角三角形になる）
  const triangle = large
    ? "border-t-[96px] border-r-[96px]"
    : "border-t-[64px] border-r-[64px]";
  const text = large
    ? "left-[-14px] top-[22px] w-[96px] text-xs"
    : "left-[-10px] top-[14px] w-[64px] text-[10px]";

  return (
    <span className={`pointer-events-none absolute left-0 top-0 z-10 overflow-hidden ${box}`}>
      <span
        aria-hidden
        className={`absolute left-0 top-0 h-0 w-0 border-r-transparent ${triangle} ${borderClass}`}
      />
      <span
        className={`absolute -rotate-45 text-center font-bold tracking-wider text-white ${text}`}
      >
        {label}
      </span>
    </span>
  );
}
