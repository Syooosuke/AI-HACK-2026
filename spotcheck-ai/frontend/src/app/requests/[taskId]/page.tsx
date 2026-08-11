"use client";

/** 画面③ 依頼公開・進行状況（docs/05-frontend.md 画面③）。10秒ごとにポーリングする。 */

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { PollingIndicator } from "@/components/task/PollingIndicator";
import { StatusTimeline } from "@/components/task/StatusTimeline";
import { Button, Card, InfoRow, SectionTitle, Skeleton } from "@/components/ui";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useToast } from "@/components/ui/Toast";
import { toMessage } from "@/lib/api/errorMessages";
import { getTask } from "@/lib/api/tasks";
import { formatDateTime, formatRemaining } from "@/lib/datetime";
import { formatCoords } from "@/lib/geo";
import type { TaskDetail } from "@/types/api";

const POLL_INTERVAL_MS = 10_000;

export default function TaskProgressPage() {
  const { taskId } = useParams<{ taskId: string }>();
  const toast = useToast();
  const [task, setTask] = useState<TaskDetail | null>(null);
  const [failed, setFailed] = useState(false);

  const load = useCallback(
    async (options: { silent?: boolean } = {}) => {
      try {
        setTask(await getTask(taskId));
        setFailed(false);
      } catch (cause) {
        setFailed(true);
        if (!options.silent) toast.error(toMessage(cause));
      }
    },
    [taskId, toast],
  );

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load({ silent: true }), POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [load]);

  if (!task) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-8 w-32" />
        <Skeleton className="h-40" />
        <Skeleton className="h-56" />
      </div>
    );
  }

  const hasResults = task.approvedWorkerCount > 0 || task.status === "completed";

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-3">
        <h1 className="text-lg font-bold leading-snug text-slate-800">{task.title}</h1>
        <StatusBadge status={task.status} />
      </div>

      {task.reviewSummary && (
        <Card className="bg-violet-50/60">
          <SectionTitle>AIによる依頼内容の要約</SectionTitle>
          <p className="text-sm text-slate-700">{task.reviewSummary}</p>
        </Card>
      )}

      <Card>
        <InfoRow label="撮影地点" value={task.locationAddress ?? formatCoords(task.locationLat, task.locationLng)} icon={<span>📍</span>} />
        <InfoRow label="撮影希望日時" value={formatDateTime(task.scheduledAt)} icon={<span>🕒</span>} />
        <InfoRow label="提出期限" value={`${formatDateTime(task.deadlineAt)}（${formatRemaining(task.deadlineAt)}）`} icon={<span>⏳</span>} />
        <InfoRow label="報酬" value={`¥${task.rewardAmount.toLocaleString()} / 人`} icon={<span>💰</span>} />
        <InfoRow
          label="受注状況"
          value={`${task.requiredWorkerCount - task.remainingSlots} / ${task.requiredWorkerCount}人`}
          icon={<span>👥</span>}
        />
        {task.requiredWorkerCount > 1 && (
          <InfoRow
            label="合格済み"
            value={`${task.approvedWorkerCount} / ${task.requiredWorkerCount}人`}
            icon={<span>✅</span>}
          />
        )}
      </Card>

      <Card>
        <SectionTitle>進行状況</SectionTitle>
        {task.timeline && <StatusTimeline steps={task.timeline} />}
      </Card>

      {hasResults && (
        <Link href={`/requests/${task.id}/results`}>
          <Button accent="client">結果を見る</Button>
        </Link>
      )}

      <PollingIndicator label="10秒ごとに進行状況を更新しています" stopped={failed} />
    </div>
  );
}
