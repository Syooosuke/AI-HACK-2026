"use client";

/** 受注した依頼の一覧（マイページ →「受注した依頼」）。 */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Card, EmptyState, Skeleton } from "@/components/ui";
import { AssignmentBadge } from "@/components/ui/StatusBadge";
import { useToast } from "@/components/ui/Toast";
import { toMessage } from "@/lib/api/errorMessages";
import { listMyAssignments, withdrawAssignment } from "@/lib/api/tasks";
import { formatDateTime } from "@/lib/datetime";
import type { MyAssignmentItem } from "@/types/api";

export default function MyAssignmentsPage() {
  const toast = useToast();
  const [items, setItems] = useState<MyAssignmentItem[] | null>(null);
  const [withdrawingId, setWithdrawingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const { assignments } = await listMyAssignments();
      setItems(assignments);
    } catch (cause) {
      setItems([]);
      toast.error(toMessage(cause));
    }
  }, [toast]);

  useEffect(() => {
    void load();
  }, [load]);

  const withdraw = async (item: MyAssignmentItem) => {
    if (!window.confirm("この依頼の受注を辞退しますか？募集枠は他のワーカーに戻ります。")) {
      return;
    }
    setWithdrawingId(item.id);
    try {
      await withdrawAssignment(item.taskId);
      toast.success("受注を辞退しました。");
      await load();
    } catch (cause) {
      toast.error(toMessage(cause));
    } finally {
      setWithdrawingId(null);
    }
  };

  return (
    <div className="space-y-4 md:mx-auto md:max-w-2xl">
      <h1 className="text-lg font-bold text-slate-800">受注中の依頼</h1>

      {items === null && (
        <div className="space-y-3">
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
        </div>
      )}
      {items?.length === 0 && (
        <EmptyState message="受注した依頼はまだありません。ホームから探してみてください。" />
      )}

      <ul className="space-y-3">
        {items?.map((item) => (
          <Card as="li" key={item.id} className="space-y-2">
            <div className="flex items-start justify-between gap-3">
              <p className="text-sm font-bold leading-snug text-slate-800">{item.title}</p>
              <AssignmentBadge status={item.status} />
            </div>
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
              <span>💰 ¥{item.rewardAmount.toLocaleString()}</span>
              <span>⏳ {formatDateTime(item.deadlineAt)}</span>
              <span>🔁 残り再撮影 {item.remainingRetakes}回</span>
            </div>
            <div className="flex gap-2">
              {item.status === "accepted" && (
                <>
                  <Link
                    href={`/jobs/${item.taskId}/capture`}
                    className="flex-1 rounded-lg bg-worker py-2 text-center text-xs font-bold text-white"
                  >
                    撮影する
                  </Link>
                  {!item.latestSubmissionId && (
                    <button
                      type="button"
                      onClick={() => void withdraw(item)}
                      disabled={withdrawingId === item.id}
                      className="rounded-lg border border-slate-300 px-3 py-2 text-xs font-bold text-slate-500 disabled:opacity-50"
                    >
                      {withdrawingId === item.id ? "辞退中…" : "辞退する"}
                    </button>
                  )}
                </>
              )}
              {item.latestSubmissionId && (
                <Link
                  href={`/jobs/${item.taskId}/status?submissionId=${item.latestSubmissionId}`}
                  className="flex-1 rounded-lg border border-slate-300 py-2 text-center text-xs font-bold text-slate-600"
                >
                  検品結果
                </Link>
              )}
            </div>
          </Card>
        ))}
      </ul>
    </div>
  );
}
