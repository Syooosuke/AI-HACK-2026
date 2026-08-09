/** 依頼カード（画面④で使用）。 */

import Link from "next/link";

import { Card } from "@/components/ui";
import { formatDateTime, formatRemaining } from "@/lib/datetime";
import { formatDistance } from "@/lib/geo";
import type { NearbyTask } from "@/types/api";

export function TaskCard({ task }: { task: NearbyTask }) {
  return (
    <Card as="li" className="space-y-3">
      <div className="flex items-start justify-between gap-3">
        <h3 className="text-sm font-bold leading-snug text-slate-800">{task.title}</h3>
        <span className="shrink-0 rounded-full bg-emerald-50 px-2 py-1 text-xs font-bold text-worker">
          残り{task.remainingSlots}枠
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-500">
        <span>📍 {formatDistance(task.distanceKm)}</span>
        <span>🕒 {formatDateTime(task.scheduledAt)}</span>
        <span>⏳ {formatRemaining(task.deadlineAt)}</span>
      </div>
      <div className="flex items-center justify-between">
        <p className="text-lg font-bold text-slate-800">
          ¥{task.rewardAmount.toLocaleString()}
        </p>
        <Link
          href={`/worker/tasks/${task.id}`}
          className="rounded-lg bg-worker px-3 py-2 text-xs font-bold text-white"
        >
          詳細を見る
        </Link>
      </div>
    </Card>
  );
}
