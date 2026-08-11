"use client";

/**
 * 投稿カード（ホーム・さがす・ハート欄で共通）。
 *
 * - 正方形のサムネイル。写真が無い依頼はサーバー側で生成した画像が入る
 * - 左下に報酬、左上に SOLD / HOT / NEW タグ（角の三角形）、右上にハート
 * - カード全体をタップすると依頼主が入力した詳細へ移動する
 */

import Link from "next/link";
import { useState } from "react";

import { CornerBadge } from "@/components/task/CornerBadge";
import { resolveApiUrl } from "@/lib/api/client";
import { toMessage } from "@/lib/api/errorMessages";
import { likeTask, unlikeTask } from "@/lib/api/social";
import { formatRemaining } from "@/lib/datetime";
import { formatDistance } from "@/lib/geo";
import type { NearbyTask } from "@/types/api";

export function TaskCard({
  task,
  onLikeChange,
  onError,
}: {
  task: NearbyTask;
  /** いいねの結果を親の一覧へ反映する（ハート欄では行を消すのに使う）。 */
  onLikeChange?: (taskId: string, liked: boolean, likeCount: number) => void;
  onError?: (message: string) => void;
}) {
  const [liked, setLiked] = useState(task.isLiked);
  const [likeCount, setLikeCount] = useState(task.likeCount);
  const [pending, setPending] = useState(false);

  const toggleLike = async (event: React.MouseEvent) => {
    // カード全体がリンクなので、ハートのタップでは遷移させない
    event.preventDefault();
    event.stopPropagation();
    if (pending) return;
    setPending(true);
    const next = !liked;
    try {
      const result = next ? await likeTask(task.id) : await unlikeTask(task.id);
      setLiked(result.liked);
      setLikeCount(result.likeCount);
      onLikeChange?.(task.id, result.liked, result.likeCount);
    } catch (cause) {
      onError?.(toMessage(cause));
    } finally {
      setPending(false);
    }
  };

  return (
    <li>
      <Link
        href={`/jobs/${task.id}`}
        className="block overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm transition hover:shadow-md"
      >
        <div className="relative aspect-square w-full bg-slate-100">
          {task.thumbnailUrl ? (
            /* eslint-disable-next-line @next/next/no-img-element -- 署名付きURLのため next/image の最適化は使わない */
            <img
              src={resolveApiUrl(task.thumbnailUrl)}
              alt={task.title}
              className="h-full w-full object-cover"
              loading="lazy"
            />
          ) : (
            <div className="flex h-full w-full items-center justify-center text-xs text-slate-400">
              画像を準備しています…
            </div>
          )}

          {/* 左上: 角を切り取る三角形のタグ（優先度が最も高い1つだけ） */}
          <CornerBadge badges={task.badges} />

          {/* 右上: いいね */}
          {!task.isMine && (
            <button
              type="button"
              onClick={toggleLike}
              disabled={pending}
              aria-label={liked ? "いいねを取り消す" : "いいねする"}
              aria-pressed={liked}
              className="absolute right-2 top-2 flex items-center gap-1 rounded-full bg-white/90 px-2 py-1 text-xs font-bold text-slate-600 shadow-sm backdrop-blur disabled:opacity-60"
            >
              <span aria-hidden className={liked ? "text-fail" : "text-slate-300"}>
                {liked ? "♥" : "♡"}
              </span>
              {likeCount > 0 && <span>{likeCount}</span>}
            </button>
          )}

          {/* 左下: 報酬 */}
          <span className="absolute bottom-2 left-2 rounded-md bg-slate-900/80 px-2 py-1 text-sm font-bold text-white">
            ¥{task.rewardAmount.toLocaleString()}
          </span>
        </div>

        <div className="space-y-1 p-3">
          <h3 className="line-clamp-2 text-sm font-bold leading-snug text-slate-800">
            {task.title}
          </h3>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] text-slate-500">
            {task.distanceKm != null && <span>📍 {formatDistance(task.distanceKm)}</span>}
            <span>⏳ {formatRemaining(task.deadlineAt)}</span>
            <span>残り{task.remainingSlots}枠</span>
          </div>
        </div>
      </Link>
    </li>
  );
}
