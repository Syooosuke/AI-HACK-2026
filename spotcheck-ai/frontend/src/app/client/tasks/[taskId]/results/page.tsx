"use client";

/**
 * 画面⑨ 結果閲覧（docs/05-frontend.md 画面⑨）。
 * 表示するのは安全処理済み画像のみ。**原本は取得も表示もしない。**
 * N人受注の場合は合格した順に随時追加表示する（D-07）。
 */

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { Card, EmptyState, InfoRow, SectionTitle, Skeleton } from "@/components/ui";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useToast } from "@/components/ui/Toast";
import { toMessage } from "@/lib/api/errorMessages";
import { getTaskResults } from "@/lib/api/tasks";
import { formatDateTime } from "@/lib/datetime";
import { formatCoords } from "@/lib/geo";
import type { TaskResults } from "@/types/api";

const POLL_INTERVAL_MS = 10_000;

export default function ResultsPage() {
  const { taskId } = useParams<{ taskId: string }>();
  const toast = useToast();
  const [data, setData] = useState<TaskResults | null>(null);

  const load = useCallback(
    async (options: { silent?: boolean } = {}) => {
      try {
        setData(await getTaskResults(taskId));
      } catch (cause) {
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

  if (!data) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-8 w-24" />
        <Skeleton className="h-64" />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-slate-800">調査結果</h1>
        <StatusBadge status={data.status} />
      </div>

      <Card className="bg-violet-50/60">
        <SectionTitle>AIによる総括</SectionTitle>
        <p className="text-sm text-slate-700">
          {data.resultSummary ?? "合格した提出がまだありません。"}
        </p>
        <p className="mt-2 text-xs text-slate-500">
          合格 {data.approvedCount} / {data.requiredWorkerCount}人
        </p>
      </Card>

      {data.results.length === 0 ? (
        <EmptyState message="まだ合格した提出がありません。ワーカーの撮影をお待ちください。" />
      ) : (
        <ul className="space-y-4">
          {data.results.map((result) => (
            <Card as="li" key={result.submissionId} className="space-y-3">
              {result.processedImageUrl ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={result.processedImageUrl}
                  alt="安全処理済みの撮影画像"
                  className="w-full rounded-xl bg-slate-100 object-cover"
                />
              ) : (
                <div className="flex h-40 items-center justify-center rounded-xl bg-slate-100 text-xs text-slate-500">
                  画像を準備中です
                </div>
              )}

              <p className="text-sm leading-relaxed text-slate-700">{result.aiSummary}</p>

              <div className="border-t border-slate-100 pt-2">
                <InfoRow label="撮影時刻" value={formatDateTime(result.capturedAt)} />
                <InfoRow
                  label="撮影位置"
                  value={result.locationLabel ?? formatCoords(result.capturedLat, result.capturedLng)}
                />
                <InfoRow
                  label="信頼度スコア"
                  value={
                    result.realityScore == null ? (
                      <span className="text-slate-400">未算出</span>
                    ) : (
                      `${result.realityScore} / 100`
                    )
                  }
                />
              </div>

              <div className="flex items-center justify-between">
                <p className="text-xs text-slate-500">
                  撮影: {result.worker.displayName}（★{result.worker.trustScore.toFixed(1)}）
                </p>
                <Link
                  href={`/client/tasks/${taskId}/results/${result.submissionId}`}
                  className="rounded-lg bg-client px-3 py-2 text-xs font-bold text-white"
                >
                  詳細を見る
                </Link>
              </div>
            </Card>
          ))}
        </ul>
      )}
    </div>
  );
}
