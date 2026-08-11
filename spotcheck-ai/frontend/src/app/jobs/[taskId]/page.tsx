"use client";

/** 画面⑤ 依頼詳細・受注（docs/05-frontend.md 画面⑤）。 */

import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { Button, Card, InfoRow, SectionTitle, Skeleton } from "@/components/ui";
import { AssignmentBadge } from "@/components/ui/StatusBadge";
import { useToast } from "@/components/ui/Toast";
import { ApiError } from "@/lib/api/client";
import { toMessage } from "@/lib/api/errorMessages";
import { acceptTask, getTask } from "@/lib/api/tasks";
import { formatDateTime, formatRemaining } from "@/lib/datetime";
import { formatCoords, formatDistanceWithWalk } from "@/lib/geo";
import type { TaskDetail } from "@/types/api";

export default function WorkerTaskDetailPage() {
  const { taskId } = useParams<{ taskId: string }>();
  const router = useRouter();
  const toast = useToast();
  const [task, setTask] = useState<TaskDetail | null>(null);
  const [accepting, setAccepting] = useState(false);

  const load = useCallback(async () => {
    try {
      const position = await currentPosition();
      setTask(await getTask(taskId, position ?? undefined));
    } catch (cause) {
      toast.error(toMessage(cause));
    }
  }, [taskId, toast]);

  useEffect(() => {
    void load();
  }, [load]);

  const accept = async () => {
    setAccepting(true);
    try {
      await acceptTask(taskId);
      toast.success("この依頼を受注しました。撮影に進んでください。");
      router.push(`/jobs/${taskId}/capture`);
    } catch (cause) {
      toast.error(toMessage(cause));
      if (cause instanceof ApiError && cause.code === "TASK_FULL") {
        router.push("/home");
        return;
      }
      setAccepting(false);
      void load();
    }
  };

  if (!task) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-8 w-40" />
        <Skeleton className="h-32" />
        <Skeleton className="h-32" />
      </div>
    );
  }

  const mine = task.myAssignment;
  const canCapture = mine?.status === "accepted";
  const isFull = task.remainingSlots <= 0 && !mine;

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-3">
        <h1 className="text-lg font-bold leading-snug text-slate-800">{task.title}</h1>
        {mine && <AssignmentBadge status={mine.status} />}
      </div>

      <Card>
        <SectionTitle>撮影条件</SectionTitle>
        {task.reviewSummary && (
          <p className="mb-2 rounded-xl bg-violet-50 px-3 py-2 text-xs text-violet-900">
            {task.reviewSummary}
          </p>
        )}
        <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-700">
          {task.description}
        </p>
      </Card>

      {task.referenceImages.length > 0 && (
        <Card>
          <SectionTitle>参考画像</SectionTitle>
          <p className="text-xs text-slate-500">
            依頼者が期待するイメージ（{task.referenceImages.length}枚）
          </p>
          {/* 参考画像の署名URL発行は Phase 4 以降で対応する。ここでは枚数のみ表示する */}
        </Card>
      )}

      <Card>
        <InfoRow
          label="現地までの距離"
          value={
            task.distanceKm == null ? "現在地不明" : formatDistanceWithWalk(task.distanceKm)
          }
          icon={<span>🚶</span>}
        />
        <InfoRow
          label="撮影地点"
          value={task.locationAddress ?? formatCoords(task.locationLat, task.locationLng)}
          icon={<span>📍</span>}
        />
        <InfoRow label="撮影希望日時" value={formatDateTime(task.scheduledAt)} icon={<span>🕒</span>} />
        <InfoRow
          label="提出期限"
          value={`${formatDateTime(task.deadlineAt)}（${formatRemaining(task.deadlineAt)}）`}
          icon={<span>⏳</span>}
        />
        <InfoRow
          label="報酬"
          value={`¥${task.rewardAmount.toLocaleString()}`}
          icon={<span>💰</span>}
        />
        <InfoRow label="残り枠" value={`${task.remainingSlots}枠`} icon={<span>👥</span>} />
      </Card>
      <p className="text-center text-[10px] text-slate-400">
        所要時間は徒歩80m/分で概算した目安です
      </p>

      {canCapture ? (
        <Button accent="worker" onClick={() => router.push(`/jobs/${taskId}/capture`)}>
          撮影に進む
        </Button>
      ) : mine ? (
        <Button
          accent="neutral"
          onClick={() =>
            router.push(
              mine.latestSubmissionId
                ? `/jobs/${taskId}/status?submissionId=${mine.latestSubmissionId}`
                : `/jobs/${taskId}`,
            )
          }
          disabled={!mine.latestSubmissionId}
        >
          検品結果を見る
        </Button>
      ) : (
        <Button accent="worker" onClick={() => void accept()} loading={accepting} disabled={isFull}>
          {isFull ? "受注枠が埋まっています" : "この依頼を受ける"}
        </Button>
      )}
    </div>
  );
}

function currentPosition(): Promise<{ lat: number; lng: number } | null> {
  if (typeof navigator === "undefined" || !navigator.geolocation) {
    return Promise.resolve(null);
  }
  return new Promise((resolve) => {
    navigator.geolocation.getCurrentPosition(
      (position) =>
        resolve({ lat: position.coords.latitude, lng: position.coords.longitude }),
      () => resolve(null),
      { timeout: 5000 },
    );
  });
}
