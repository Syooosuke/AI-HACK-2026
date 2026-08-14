"use client";

/** 自分が出した依頼の一覧（マイページ →「出した依頼」/ 画面③への入口）。 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { Button, Card, EmptyState, Skeleton } from "@/components/ui";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useToast } from "@/components/ui/Toast";
import { toMessage } from "@/lib/api/errorMessages";
import { duplicateTask, listMyTasks } from "@/lib/api/tasks";
import {
  formatDateTime,
  formatRemaining,
  isoToLocalInput,
  localInputToIso,
  minutesFromNow,
} from "@/lib/datetime";
import { saveReview } from "@/lib/reviewHandoff";
import type { TaskListItem } from "@/types/api";

export default function MyRequestsPage() {
  const router = useRouter();
  const toast = useToast();
  const [tasks, setTasks] = useState<TaskListItem[] | null>(null);
  const [duplicateId, setDuplicateId] = useState<string | null>(null);
  const [scheduledAt, setScheduledAt] = useState("");
  const [deadlineAt, setDeadlineAt] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const openDuplicate = (task: TaskListItem) => {
    const durationMinutes = Math.max(
      60,
      Math.round(
        (new Date(task.deadlineAt).getTime() - new Date(task.scheduledAt).getTime()) / 60_000,
      ),
    );
    setDuplicateId(task.id);
    setScheduledAt(isoToLocalInput(minutesFromNow(60)));
    setDeadlineAt(isoToLocalInput(minutesFromNow(60 + durationMinutes)));
  };

  const submitDuplicate = async () => {
    if (!duplicateId) return;
    if (new Date(scheduledAt).getTime() <= Date.now()) {
      toast.error("撮影希望日時は現在時刻より後を指定してください。");
      return;
    }
    if (new Date(deadlineAt) < new Date(scheduledAt)) {
      toast.error("期限は撮影希望日時以降を指定してください。");
      return;
    }

    setSubmitting(true);
    try {
      const review = await duplicateTask(duplicateId, {
        scheduledAt: localInputToIso(scheduledAt),
        deadlineAt: localInputToIso(deadlineAt),
      });
      saveReview(review);
      router.push("/requests/new/review");
    } catch (cause) {
      toast.error(toMessage(cause));
      setSubmitting(false);
    }
  };

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
    <div className="space-y-4 md:mx-auto md:max-w-2xl">
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
            {duplicateId === task.id ? (
              <div className="space-y-3 rounded-xl bg-blue-50 p-3">
                <p className="text-xs font-bold text-client">日時を変更して再投稿</p>
                <div className="grid gap-2 sm:grid-cols-2">
                  <label className="text-xs text-slate-600">
                    <span className="mb-1 block">撮影希望日時</span>
                    <input
                      type="datetime-local"
                      value={scheduledAt}
                      onChange={(event) => setScheduledAt(event.target.value)}
                      className="w-full rounded-lg border border-slate-300 bg-white px-2 py-2"
                    />
                  </label>
                  <label className="text-xs text-slate-600">
                    <span className="mb-1 block">期限</span>
                    <input
                      type="datetime-local"
                      value={deadlineAt}
                      onChange={(event) => setDeadlineAt(event.target.value)}
                      className="w-full rounded-lg border border-slate-300 bg-white px-2 py-2"
                    />
                  </label>
                </div>
                <p className="text-xs text-slate-500">
                  場所・報酬・人数・依頼内容・参考画像は元の依頼を引き継ぎます。
                </p>
                <div className="flex gap-2">
                  <Button
                    accent="neutral"
                    className="py-2.5"
                    onClick={() => setDuplicateId(null)}
                    disabled={submitting}
                  >
                    キャンセル
                  </Button>
                  <Button
                    accent="client"
                    className="py-2.5"
                    onClick={() => void submitDuplicate()}
                    loading={submitting}
                    disabled={!scheduledAt || !deadlineAt}
                  >
                    AI審査して再投稿
                  </Button>
                </div>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => openDuplicate(task)}
                className="text-xs font-bold text-client hover:underline"
              >
                ⧉ この依頼を複製
              </button>
            )}
          </Card>
        ))}
      </ul>
    </div>
  );
}
