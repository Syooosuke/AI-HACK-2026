"use client";

/** 下部タブ「お知らせ」。10秒ごとにポーリングする（画面③と同じ間隔）。 */

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { PollingIndicator } from "@/components/task/PollingIndicator";
import { EmptyState, Skeleton } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";
import { toMessage } from "@/lib/api/errorMessages";
import {
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
} from "@/lib/api/notifications";
import { formatRelative } from "@/lib/datetime";
import type { NotificationItem, NotificationType } from "@/types/api";

const POLL_INTERVAL_MS = 10_000;
const NOTIFICATIONS_PER_PAGE = 10;

/** 取得がこれより長引いたときだけ、読み込み中の表示を出す。 */
const SLOW_FETCH_MS = 800;

const TYPE_ICON: Record<NotificationType, string> = {
  task_approved: "✅",
  task_needs_info: "✍️",
  task_rejected: "🚫",
  task_accepted: "🙋",
  submission_approved: "🎉",
  submission_retake: "📷",
  submission_failed: "⚠️",
  task_completed: "🏁",
  task_expired: "⌛",
};

/** 依頼者向けの通知は依頼の進行状況画面へ、ワーカー向けは受注中タスクの状況画面へ。 */
function routeFor(notification: NotificationItem): string | null {
  if (!notification.taskId) return null;
  switch (notification.type) {
    // 再撮影の指示は「撮り直す」ことが次の行動なので、カメラへ直接入る。
    // 検品結果を見に行かせると、そこから撮影画面へ移る操作が1つ増える
    case "submission_retake":
      return `/jobs/${notification.taskId}/capture`;
    case "submission_approved":
    case "submission_failed":
      return `/jobs/${notification.taskId}/status`;
    default:
      return `/requests/${notification.taskId}`;
  }
}

export default function NotificationsPage() {
  const router = useRouter();
  const toast = useToast();
  const [notifications, setNotifications] = useState<NotificationItem[] | null>(null);
  const [loadingSlow, setLoadingSlow] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);

  const load = useCallback(
    async (options: { silent?: boolean } = {}) => {
      // 取得がこの時間を超えたときだけ「確認しています」を出す
      const slowTimer = window.setTimeout(() => setLoadingSlow(true), SLOW_FETCH_MS);
      try {
        const { notifications: items } = await listNotifications();
        setNotifications(items);
      } catch (cause) {
        if (!options.silent) toast.error(toMessage(cause));
      } finally {
        window.clearTimeout(slowTimer);
        setLoadingSlow(false);
      }
    },
    [toast],
  );

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load({ silent: true }), POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [load]);

  const unreadCount = notifications?.filter((item) => !item.readAt).length ?? 0;
  const totalPages = Math.max(
    1,
    Math.ceil((notifications?.length ?? 0) / NOTIFICATIONS_PER_PAGE),
  );
  const pageNotifications =
    notifications?.slice(
      (currentPage - 1) * NOTIFICATIONS_PER_PAGE,
      currentPage * NOTIFICATIONS_PER_PAGE,
    ) ?? [];

  // 自動更新などで件数が減ったとき、存在しないページを表示し続けない。
  useEffect(() => {
    setCurrentPage((page) => Math.min(page, totalPages));
  }, [totalPages]);

  const moveToPage = (page: number) => {
    setCurrentPage(page);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const openNotification = (notification: NotificationItem) => {
    if (!notification.readAt) {
      setNotifications(
        (current) =>
          current?.map((item) =>
            item.id === notification.id ? { ...item, readAt: new Date().toISOString() } : item,
          ) ?? null,
      );
      // 遷移を待たせないため、既読化は裏側で行う。失敗しても静かに無視する
      markNotificationRead(notification.id).catch(() => {});
    }
    const href = routeFor(notification);
    if (href) router.push(href);
  };

  const readAll = async () => {
    const now = new Date().toISOString();
    setNotifications(
      (current) => current?.map((item) => ({ ...item, readAt: item.readAt ?? now })) ?? null,
    );
    try {
      await markAllNotificationsRead();
    } catch (cause) {
      toast.error(toMessage(cause));
    }
  };

  if (!notifications) {
    return (
      <div className="space-y-3 md:mx-auto md:max-w-2xl">
        <Skeleton className="h-8 w-32" />
        <Skeleton className="h-16" />
        <Skeleton className="h-16" />
        <Skeleton className="h-16" />
      </div>
    );
  }

  return (
    <div className="space-y-4 md:mx-auto md:max-w-2xl">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-lg font-bold text-slate-800">お知らせ</h1>
        {unreadCount > 0 && (
          <button
            type="button"
            onClick={() => void readAll()}
            className="text-xs font-bold text-client hover:underline"
          >
            すべて既読にする
          </button>
        )}
      </div>

      {notifications.length === 0 ? (
        <EmptyState message="お知らせはまだありません。検品結果は「マイページ」から確認できます。" />
      ) : (
        <ul className="space-y-2">
          {pageNotifications.map((notification) => (
            <li key={notification.id}>
              <button
                type="button"
                onClick={() => openNotification(notification)}
                className={`flex w-full items-start gap-3 rounded-2xl border px-4 py-3 text-left shadow-sm transition ${
                  notification.readAt ? "border-slate-200 bg-white" : "border-client/30 bg-blue-50/60"
                }`}
              >
                <span aria-hidden className="text-xl leading-none">
                  {TYPE_ICON[notification.type]}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2">
                    <span className="truncate text-sm font-bold text-slate-800">
                      {notification.title}
                    </span>
                    {!notification.readAt && (
                      <span aria-hidden className="h-1.5 w-1.5 shrink-0 rounded-full bg-client" />
                    )}
                  </span>
                  {notification.body && (
                    <span className="mt-0.5 block text-xs text-slate-500">{notification.body}</span>
                  )}
                  <span className="mt-1 block text-[11px] text-slate-400">
                    {formatRelative(notification.createdAt)}
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}

      {notifications.length > NOTIFICATIONS_PER_PAGE && (
        <nav aria-label="お知らせのページ" className="flex items-center justify-center gap-2 pt-1">
          <button
            type="button"
            onClick={() => moveToPage(currentPage - 1)}
            disabled={currentPage === 1}
            className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-bold text-slate-600 disabled:cursor-not-allowed disabled:opacity-40"
          >
            前へ
          </button>
          {Array.from({ length: totalPages }, (_, index) => index + 1).map((page) => (
            <button
              key={page}
              type="button"
              onClick={() => moveToPage(page)}
              aria-current={currentPage === page ? "page" : undefined}
              className={`h-9 min-w-9 rounded-lg px-2 text-xs font-bold transition ${
                currentPage === page
                  ? "bg-client text-white"
                  : "border border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
              }`}
            >
              {page}
            </button>
          ))}
          <button
            type="button"
            onClick={() => moveToPage(currentPage + 1)}
            disabled={currentPage === totalPages}
            className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-bold text-slate-600 disabled:cursor-not-allowed disabled:opacity-40"
          >
            次へ
          </button>
        </nav>
      )}

      {/*
        自動更新は10秒ごとに静かに走る。取得はふつう一瞬で終わるので、
        「確認しています」を常時出しても情報にならず、動き続けるスピナーが目障りになる。
        **もたついたときだけ**出す（下の SLOW_FETCH_MS）。
      */}
      {loadingSlow && <PollingIndicator label="最新のお知らせを確認しています" />}
    </div>
  );
}
