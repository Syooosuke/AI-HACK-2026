"use client";

/** 自分が出した依頼の一覧（マイページ →「出した依頼」/ 画面③への入口）。 */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Button, Card, EmptyState, Skeleton } from "@/components/ui";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useToast } from "@/components/ui/Toast";
import { toMessage } from "@/lib/api/errorMessages";
import { listMyTasks } from "@/lib/api/tasks";
import { formatDateTime, formatRemaining } from "@/lib/datetime";
import type { TaskListItem } from "@/types/api";

export default function MyRequestsPage() {
  const toast = useToast();
  const [tasks, setTasks] = useState<TaskListItem[] | null>(null);

  const load = useCallback(async () => {
    try {
      const { tasks: fetched } = await listMyTasks();
      setTasks(fetched);
    } catch (cause) {
      setTasks([]);
      toast.error(toMessage(cause));
    }
  }, [toast]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-slate-800">出した依頼</h1>
        <Link
          href="/requests/new"
          className="rounded-xl bg-client px-3 py-2 text-xs font-bold text-white"
        >
          ＋ 新規依頼
        </Link>
      </div>

      {tasks === null && (
        <div className="space-y-3">
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
        </div>
      )}

      {tasks?.length === 0 && (
        <EmptyState
          message="まだ依頼がありません。"
          action={
            <Link href="/requests/new">
              <Button accent="client">最初の依頼を作成する</Button>
            </Link>
          }
        />
      )}

      <ul className="space-y-3">
        {tasks?.map((task) => (
          <Card as="li" key={task.id} className="space-y-2">
            <div className="flex items-start justify-between gap-3">
              <Link
                href={`/requests/${task.id}`}
                className="text-sm font-bold leading-snug text-slate-800 hover:underline"
              >
                {task.title}
              </Link>
              <StatusBadge status={task.status} />
            </div>
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
              <span>💰 ¥{task.rewardAmount.toLocaleString()}</span>
              <span>
                👥 {task.approvedWorkerCount} / {task.requiredWorkerCount}人 合格
              </span>
              <span>🕒 {formatDateTime(task.scheduledAt)}</span>
              <span>⏳ {formatRemaining(task.deadlineAt)}</span>
            </div>
          </Card>
        ))}
      </ul>
    </div>
  );
}
