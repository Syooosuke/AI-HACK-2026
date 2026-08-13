"use client";

/** 画面⑩ 結果詳細 / レポート（docs/05-frontend.md 画面⑩）。 */

import { useParams } from "next/navigation";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Button, Card, EmptyState, InfoRow, SectionTitle, Skeleton } from "@/components/ui";
import { Avatar } from "@/components/ui/Avatar";
import { useToast } from "@/components/ui/Toast";
import { TrustBar, TrustGauge } from "@/components/ui/TrustGauge";
import { toMessage } from "@/lib/api/errorMessages";
import { resolveApiUrl } from "@/lib/api/client";
import { getTask, getTaskResults } from "@/lib/api/tasks";
import { createWorkerReview } from "@/lib/api/submissions";
import { formatDateTime } from "@/lib/datetime";
import { formatCoords } from "@/lib/geo";
import type { TaskDetail, TaskResultItem, WorkerReviewTag } from "@/types/api";

const REVIEW_TAGS: Array<{ value: WorkerReviewTag; label: string }> = [
  { value: "as_requested", label: "依頼どおり" },
  { value: "clear_photo", label: "写真が見やすい" },
  { value: "fast_response", label: "対応が早い" },
  { value: "accurate_location", label: "位置情報が正確" },
];

export default function ResultDetailPage() {
  const { taskId, submissionId } = useParams<{ taskId: string; submissionId: string }>();
  const toast = useToast();
  const [task, setTask] = useState<TaskDetail | null>(null);
  const [result, setResult] = useState<TaskResultItem | null | undefined>(undefined);
  const [openBreakdown, setOpenBreakdown] = useState(false);
  const [rating, setRating] = useState(0);
  const [reviewTags, setReviewTags] = useState<WorkerReviewTag[]>([]);
  const [reviewComment, setReviewComment] = useState("");
  const [reviewing, setReviewing] = useState(false);

  const load = useCallback(async () => {
    try {
      const [detail, results] = await Promise.all([getTask(taskId), getTaskResults(taskId)]);
      setTask(detail);
      setResult(results.results.find((item) => item.submissionId === submissionId) ?? null);
    } catch (cause) {
      setResult(null);
      toast.error(toMessage(cause));
    }
  }, [taskId, submissionId, toast]);

  useEffect(() => {
    void load();
  }, [load]);

  const submitReview = async () => {
    if (!result || rating === 0) return;
    setReviewing(true);
    try {
      const review = await createWorkerReview(result.submissionId, {
        rating,
        tags: reviewTags,
        comment: reviewComment.trim() || undefined,
      });
      setResult({ ...result, workerReview: review });
      toast.success("ワーカーを評価しました。");
    } catch (cause) {
      toast.error(toMessage(cause));
    } finally {
      setReviewing(false);
    }
  };

  if (result === undefined) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-8 w-32" />
        <Skeleton className="h-64" />
      </div>
    );
  }

  if (result === null) {
    return <EmptyState message="この提出は見つかりませんでした。" />;
  }

  return (
    <div className="space-y-5 md:mx-auto md:max-w-2xl">
      <h1 className="text-lg font-bold text-slate-800">調査レポート</h1>

      {task && (
        <Card>
          <SectionTitle>依頼内容（原文）</SectionTitle>
          <p className="text-sm font-bold text-slate-800">{task.title}</p>
          <p className="mt-1 whitespace-pre-wrap text-sm leading-relaxed text-slate-600">
            {task.description}
          </p>
        </Card>
      )}

      <Card className="bg-violet-50/60">
        <SectionTitle>回答サマリー（AI要約）</SectionTitle>
        <p className="text-sm leading-relaxed text-slate-700">{result.aiSummary}</p>
      </Card>

      <Card className="space-y-2">
        <SectionTitle>画像（安全処理済み）</SectionTitle>
        {result.processedImageUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={resolveApiUrl(result.processedImageUrl)}
            alt="安全処理済みの撮影画像"
            className="w-full rounded-xl bg-slate-100"
          />
        ) : (
          <div className="flex h-40 items-center justify-center rounded-xl bg-slate-100 text-xs text-slate-500">
            画像を準備中です
          </div>
        )}
      </Card>

      <Card>
        <SectionTitle>GPS / タイムスタンプ</SectionTitle>
        <InfoRow label="緯度・経度" value={formatCoords(result.capturedLat, result.capturedLng)} />
        <InfoRow label="撮影時刻" value={formatDateTime(result.capturedAt)} />
        {result.locationLabel && <InfoRow label="住所" value={result.locationLabel} />}
      </Card>

      <Card>
        <button
          type="button"
          onClick={() => setOpenBreakdown((open) => !open)}
          className="flex w-full items-center justify-between"
        >
          <SectionTitle>Reality Score / 信頼度</SectionTitle>
          <span className="flex items-center gap-2">
            <TrustBar score={result.realityScore} label="Reality Score" />
            <span className="text-slate-400">{openBreakdown ? "▲" : "▼"}</span>
          </span>
        </button>
        {openBreakdown && (
          <div className="mt-2 border-t border-slate-100 pt-2">
            {result.locationCheck ? (
              <>
                <InfoRow
                  label="依頼地点からの距離"
                  value={`${result.locationCheck.distance_m ?? "—"} m`}
                />
                <InfoRow
                  label="距離の許容範囲内"
                  value={result.locationCheck.within_tolerance ? "はい" : "いいえ"}
                />
                <InfoRow
                  label="端末時刻とのずれ"
                  value={`${result.locationCheck.timestamp_delta_seconds ?? "—"} 秒`}
                />
                <InfoRow
                  label="時刻の整合"
                  value={result.locationCheck.timestamp_consistent ? "はい" : "いいえ"}
                />
                {result.locationCheck.pending_checks?.length ? (
                  <p className="mt-2 text-xs text-slate-400">
                    未実装のチェック: {result.locationCheck.pending_checks.join(", ")}
                  </p>
                ) : null}
              </>
            ) : (
              <p className="text-xs text-slate-500">内訳がありません。</p>
            )}
          </div>
        )}
      </Card>

      <Card>
        <SectionTitle>ワーカー評価</SectionTitle>
        <div className="flex items-center gap-4">
          <Avatar name={result.worker.displayName} src={result.worker.avatarUrl} size="md" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-bold text-slate-800">
              {result.worker.displayName}
            </p>
            <p className="text-xs text-slate-500">信頼度スコア</p>
          </div>
          <TrustGauge score={result.worker.trustScore} label="ワーカーの信頼度スコア" size="sm" />
        </div>
        <Link
          href={`/users/${result.worker.id}`}
          className="mt-3 block text-right text-xs font-bold text-client underline"
        >
          プロフィールを見る
        </Link>
        <div className="mt-4 border-t border-slate-100 pt-4">
          {result.workerReview ? (
            <div className="space-y-2">
              <p className="text-lg tracking-wide text-amber-400" aria-label={`${result.workerReview.rating}つ星`}>
                {"★".repeat(result.workerReview.rating)}
                <span className="text-slate-200">{"★".repeat(5 - result.workerReview.rating)}</span>
              </p>
              {result.workerReview.tags.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {result.workerReview.tags.map((tag) => (
                    <span key={tag} className="rounded-full bg-amber-50 px-2.5 py-1 text-xs text-amber-800">
                      {REVIEW_TAGS.find((item) => item.value === tag)?.label ?? tag}
                    </span>
                  ))}
                </div>
              )}
              {result.workerReview.comment && (
                <p className="text-sm text-slate-600">{result.workerReview.comment}</p>
              )}
              <p className="text-xs text-slate-400">評価済みです</p>
            </div>
          ) : (
            <div className="space-y-3">
              <p className="text-sm font-bold text-slate-700">今回の仕事を評価する</p>
              <div className="flex gap-1" role="group" aria-label="星評価">
                {[1, 2, 3, 4, 5].map((star) => (
                  <button
                    key={star}
                    type="button"
                    onClick={() => setRating(star)}
                    className={`text-3xl ${star <= rating ? "text-amber-400" : "text-slate-200"}`}
                    aria-label={`${star}つ星`}
                  >
                    ★
                  </button>
                ))}
              </div>
              <div className="flex flex-wrap gap-2">
                {REVIEW_TAGS.map((tag) => {
                  const selected = reviewTags.includes(tag.value);
                  return (
                    <button
                      key={tag.value}
                      type="button"
                      onClick={() =>
                        setReviewTags((current) =>
                          selected
                            ? current.filter((value) => value !== tag.value)
                            : [...current, tag.value],
                        )
                      }
                      className={`rounded-full border px-3 py-1.5 text-xs ${
                        selected
                          ? "border-amber-400 bg-amber-50 text-amber-800"
                          : "border-slate-200 text-slate-600"
                      }`}
                    >
                      {tag.label}
                    </button>
                  );
                })}
              </div>
              <textarea
                rows={3}
                maxLength={500}
                value={reviewComment}
                onChange={(event) => setReviewComment(event.target.value)}
                placeholder="コメント（任意）"
                className="w-full rounded-xl border border-slate-300 px-3 py-2.5 text-sm"
              />
              <Button
                accent="client"
                disabled={rating === 0}
                loading={reviewing}
                onClick={() => void submitReview()}
              >
                評価を送信
              </Button>
            </div>
          )}
        </div>
      </Card>

      <div className="no-print">
        <Button accent="neutral" onClick={() => window.print()}>
          レポートを印刷
        </Button>
      </div>
    </div>
  );
}
