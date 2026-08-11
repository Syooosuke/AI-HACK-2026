"use client";

/**
 * 画面⑤ 依頼詳細・受注（docs/05-frontend.md 画面⑤）。
 * 投稿カードをタップするとここへ来る。依頼主が入力した内容を一通り表示する。
 */

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { StreetViewPanel } from "@/components/map/StreetViewPanel";
import { CornerBadge } from "@/components/task/CornerBadge";
import { Button, Card, InfoRow, SectionTitle, Skeleton } from "@/components/ui";
import { Avatar } from "@/components/ui/Avatar";
import { AssignmentBadge } from "@/components/ui/StatusBadge";
import { useToast } from "@/components/ui/Toast";
import { TrustBar } from "@/components/ui/TrustGauge";
import { ApiError, resolveApiUrl } from "@/lib/api/client";
import { likeTask, unlikeTask } from "@/lib/api/social";
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
  const [likePending, setLikePending] = useState(false);

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

  const toggleLike = async () => {
    if (!task || likePending) return;
    setLikePending(true);
    try {
      const result = task.isLiked
        ? await unlikeTask(task.id)
        : await likeTask(task.id);
      setTask({ ...task, isLiked: result.liked, likeCount: result.likeCount });
    } catch (cause) {
      toast.error(toMessage(cause));
    } finally {
      setLikePending(false);
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
    /* PCでは画像を左に固定し、右側で内容を読ませる */
    <div className="space-y-5 lg:grid lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)] lg:items-start lg:gap-8 lg:space-y-0">
      {task.thumbnailUrl && (
        <div className="relative overflow-hidden rounded-2xl bg-slate-100 lg:sticky lg:top-20">
          {/* eslint-disable-next-line @next/next/no-img-element -- 署名付きURLのため最適化は使わない */}
          <img
            src={resolveApiUrl(task.thumbnailUrl)}
            alt={task.title}
            className="aspect-square w-full object-cover"
          />
          <CornerBadge badges={task.badges} size="lg" />
        </div>
      )}

      <div className="space-y-5">
        <div className="flex items-start justify-between gap-3">
          <h1 className="text-lg font-bold leading-snug text-slate-800">
            {task.title}
          </h1>
          <div className="flex shrink-0 items-center gap-2">
            {mine && <AssignmentBadge status={mine.status} />}
            {!task.isMine && (
              <button
                type="button"
                onClick={() => void toggleLike()}
                disabled={likePending}
                aria-label={task.isLiked ? "いいねを取り消す" : "いいねする"}
                aria-pressed={task.isLiked}
                className="flex items-center gap-1 rounded-full border border-slate-200 px-3 py-1.5 text-xs font-bold text-slate-600 disabled:opacity-60"
              >
                <span
                  aria-hidden
                  className={task.isLiked ? "text-fail" : "text-slate-300"}
                >
                  {task.isLiked ? "♥" : "♡"}
                </span>
                {task.likeCount}
              </button>
            )}
          </div>
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
            <p className="mb-2 text-xs text-slate-500">
              依頼者が期待するイメージ（{task.referenceImages.length}枚）
            </p>
            <ul className="grid grid-cols-3 gap-2">
              {task.referenceImages.map((image) => (
                <li
                  key={image.id}
                  className="overflow-hidden rounded-xl bg-slate-100"
                >
                  {/* eslint-disable-next-line @next/next/no-img-element -- 署名付きURLのため最適化は使わない */}
                  <img
                    src={resolveApiUrl(image.imageUrl)}
                    alt="参考画像"
                    className="aspect-square w-full object-cover"
                    loading="lazy"
                  />
                </li>
              ))}
            </ul>
          </Card>
        )}

        <Card className="space-y-2">
          <SectionTitle>現地の様子（ストリートビュー）</SectionTitle>
          <p className="text-xs text-slate-500">
            撮影地点の周辺を実景で確認できます。ドラッグで見回せます。
          </p>
          <StreetViewPanel position={{ lat: task.locationLat, lng: task.locationLng }} />
        </Card>

        <Card>
          <InfoRow
            label="現地までの距離"
            value={
              task.distanceKm == null
                ? "現在地不明"
                : formatDistanceWithWalk(task.distanceKm)
            }
            icon={<span>🚶</span>}
          />
          <InfoRow
            label="撮影地点"
            value={
              task.locationAddress ??
              formatCoords(task.locationLat, task.locationLng)
            }
            icon={<span>📍</span>}
          />
          <InfoRow
            label="撮影希望日時"
            value={formatDateTime(task.scheduledAt)}
            icon={<span>🕒</span>}
          />
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
          <InfoRow
            label="残り枠"
            value={`${task.remainingSlots}枠`}
            icon={<span>👥</span>}
          />
          {task.owner && (
            <InfoRow
              label="依頼主"
              value={
                // 受注前に「どんな依頼者か」を確かめられるよう、公開プロフィールへ遷移させる
                <Link
                  href={`/users/${task.owner.id}`}
                  className="flex items-center justify-end gap-2 hover:opacity-80"
                >
                  <Avatar name={task.owner.displayName} src={task.owner.avatarUrl} size="xs" />
                  <span className="flex flex-col items-end">
                    <span className="max-w-[7rem] truncate font-medium text-client">
                      {task.owner.displayName}
                    </span>
                    <span className="text-[10px] text-slate-500">
                      {task.owner.completionRate == null
                        ? "依頼実績なし"
                        : `完了率 ${Math.round(task.owner.completionRate * 100)}%・依頼${task.owner.publishedTaskCount}件`}
                    </span>
                  </span>
                  <TrustBar score={task.owner.trustScore} label="依頼主の信頼度スコア" />
                  <span aria-hidden className="text-slate-300">
                    ›
                  </span>
                </Link>
              }
              icon={<span>🧑‍💼</span>}
            />
          )}
          <InfoRow
            label="閲覧・いいね"
            value={`${task.viewCount}回 / ${task.likeCount}件`}
            icon={<span>👀</span>}
          />
        </Card>
        <p className="text-center text-[10px] text-slate-400">
          所要時間は徒歩80m/分で概算した目安です
        </p>

        {canCapture ? (
          <Button
            accent="worker"
            onClick={() => router.push(`/jobs/${taskId}/capture`)}
          >
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
          <Button
            accent="worker"
            onClick={() => void accept()}
            loading={accepting}
            disabled={isFull}
          >
            {isFull ? "受注枠が埋まっています" : "この依頼を受ける"}
          </Button>
        )}
      </div>
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
        resolve({
          lat: position.coords.latitude,
          lng: position.coords.longitude,
        }),
      () => resolve(null),
      { timeout: 5000 },
    );
  });
}
