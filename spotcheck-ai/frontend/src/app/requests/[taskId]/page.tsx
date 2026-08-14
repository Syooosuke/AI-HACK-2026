"use client";

/** 画面③ 依頼公開・進行状況（docs/05-frontend.md 画面③）。10秒ごとにポーリングする。 */

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { PollingIndicator } from "@/components/task/PollingIndicator";
import { StatusTimeline } from "@/components/task/StatusTimeline";
import { TimeWindow } from "@/components/task/TimeWindow";
import { Button, Card, InfoRow, SectionTitle, Skeleton } from "@/components/ui";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useToast } from "@/components/ui/Toast";
import { toMessage } from "@/lib/api/errorMessages";
import { cancelTask, extendTaskDeadline, getTask } from "@/lib/api/tasks";
import { isoToLocalInput, localInputToIso } from "@/lib/datetime";
import { formatCoords } from "@/lib/geo";
import type { TaskDetail } from "@/types/api";

const POLL_INTERVAL_MS = 10_000;

export default function TaskProgressPage() {
  const { taskId } = useParams<{ taskId: string }>();
  const router = useRouter();
  const toast = useToast();
  const [task, setTask] = useState<TaskDetail | null>(null);
  const [failed, setFailed] = useState(false);
  const [showDeadlineForm, setShowDeadlineForm] = useState(false);
  const [newDeadlineAt, setNewDeadlineAt] = useState("");
  const [extending, setExtending] = useState(false);
  const [cancelling, setCancelling] = useState(false);

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
  const canExtendDeadline = task.status === "open" || task.status === "in_progress";
  // バックエンドの CANCELLABLE_STATUSES と揃える。受注が入った時点で in_progress になり、
  // 取り下げはできなくなる（撮影に向かっているワーカーがいるため）
  const canCancel =
    task.status === "screening" || task.status === "needs_info" || task.status === "open";

  const openDeadlineForm = () => {
    const defaultDeadline = new Date(new Date(task.deadlineAt).getTime() + 24 * 60 * 60 * 1000);
    setNewDeadlineAt(isoToLocalInput(defaultDeadline));
    setShowDeadlineForm(true);
  };

  const cancel = async () => {
    if (
      !window.confirm(
        "この依頼の募集を取り下げますか？取り下げると元に戻せません（同じ内容で作り直すことはできます）。",
      )
    ) {
      return;
    }
    setCancelling(true);
    try {
      await cancelTask(task.id);
      toast.success("募集を取り下げました。");
      router.push("/requests");
    } catch (cause) {
      toast.error(toMessage(cause));
      setCancelling(false);
      void load();
    }
  };

  const extendDeadline = async () => {
    if (!newDeadlineAt) return;
    if (new Date(newDeadlineAt) <= new Date(task.deadlineAt)) {
      toast.error("現在の期限より後を指定してください。");
      return;
    }
    setExtending(true);
    try {
      const { task: updated } = await extendTaskDeadline(task.id, localInputToIso(newDeadlineAt));
      setTask({ ...task, deadlineAt: updated.deadlineAt });
      setShowDeadlineForm(false);
      toast.success("期限を延長しました。");
    } catch (cause) {
      toast.error(toMessage(cause));
    } finally {
      setExtending(false);
    }
  };

  return (
    <div className="space-y-5 md:mx-auto md:max-w-2xl">
      <div className="flex items-start justify-between gap-3">
        <h1 className="text-lg font-bold leading-snug text-slate-800">{task.title}</h1>
        <StatusBadge status={task.status} />
      </div>

      {/*
        AIによる「依頼内容の要約」はここには出さない。
        自分が書いた依頼を要約して見せられても、依頼者にとっては情報が増えない。
        （要約は審査結果画面と、ワーカー向けの依頼詳細では引き続き使う）
      */}

      {/*
        撮影の時間帯は依頼者側でも「幅」で見せる。ワーカー向けと同じ図にしておくと、
        依頼者が指定した幅がそのまま相手にどう見えているかが分かる
      */}
      <TimeWindow from={task.scheduledAt} to={task.deadlineAt} audience="client" showRemaining />

      <Card>
        <InfoRow label="撮影地点" value={task.locationAddress ?? formatCoords(task.locationLat, task.locationLng)} icon={<span>📍</span>} />
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
        {canExtendDeadline && (
          <div className="mt-3 border-t border-slate-100 pt-3">
            {showDeadlineForm ? (
              <div className="space-y-2">
                <label className="block text-xs font-bold text-slate-500">
                  新しい期限
                  <input
                    type="datetime-local"
                    value={newDeadlineAt}
                    min={isoToLocalInput(new Date(task.deadlineAt))}
                    onChange={(event) => setNewDeadlineAt(event.target.value)}
                    className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2.5 text-sm font-normal text-slate-800"
                  />
                </label>
                <p className="text-xs text-slate-500">現在の期限より後の日時を指定してください。</p>
                <div className="flex gap-2">
                  <Button
                    accent="neutral"
                    className="py-2.5"
                    onClick={() => setShowDeadlineForm(false)}
                    disabled={extending}
                  >
                    キャンセル
                  </Button>
                  <Button
                    accent="client"
                    className="py-2.5"
                    onClick={() => void extendDeadline()}
                    loading={extending}
                    disabled={!newDeadlineAt}
                  >
                    期限を延長する
                  </Button>
                </div>
              </div>
            ) : (
              <button
                type="button"
                onClick={openDeadlineForm}
                className="text-xs font-bold text-client hover:underline"
              >
                期限を延長する
              </button>
            )}
          </div>
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

      {/*
        募集の取り下げ。**受注が入る前に限る**（受注後に取り下げられると、
        現地へ向かっているワーカーの労力が無駄になるため）。
      */}
      {canCancel && (
        <div className="space-y-2 rounded-2xl border border-slate-200 bg-white px-4 py-4">
          <p className="text-xs text-slate-500">
            まだ誰も受注していないため、この依頼は取り下げられます。取り下げると元に戻せません。
          </p>
          <Button accent="neutral" onClick={() => void cancel()} loading={cancelling}>
            募集を取り下げる
          </Button>
        </div>
      )}

      <PollingIndicator label="10秒ごとに進行状況を更新しています" stopped={failed} />
    </div>
  );
}
