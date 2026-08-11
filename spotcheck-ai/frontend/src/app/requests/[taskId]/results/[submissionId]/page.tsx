"use client";

/** 画面⑩ 結果詳細 / レポート（docs/05-frontend.md 画面⑩）。 */

import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { Button, Card, EmptyState, InfoRow, SectionTitle, Skeleton } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";
import { toMessage } from "@/lib/api/errorMessages";
import { resolveApiUrl } from "@/lib/api/client";
import { getTask, getTaskResults } from "@/lib/api/tasks";
import { formatDateTime } from "@/lib/datetime";
import { formatCoords } from "@/lib/geo";
import type { TaskDetail, TaskResultItem } from "@/types/api";

export default function ResultDetailPage() {
  const { taskId, submissionId } = useParams<{ taskId: string; submissionId: string }>();
  const toast = useToast();
  const [task, setTask] = useState<TaskDetail | null>(null);
  const [result, setResult] = useState<TaskResultItem | null | undefined>(undefined);
  const [openBreakdown, setOpenBreakdown] = useState(false);

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

  const stars = "★".repeat(Math.round(result.worker.trustScore)).padEnd(5, "☆");

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
            <span className="rounded-full bg-ai px-2.5 py-1 text-xs font-bold text-white">
              {result.realityScore == null ? "未算出" : `${result.realityScore} / 100`}
            </span>
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
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-full bg-slate-100 text-lg">
            👤
          </span>
          <div>
            <p className="text-sm font-bold text-slate-800">{result.worker.displayName}</p>
            <p className="text-sm text-amber-500">
              {stars}
              <span className="ml-1 text-xs text-slate-500">
                {result.worker.trustScore.toFixed(1)}
              </span>
            </p>
          </div>
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
