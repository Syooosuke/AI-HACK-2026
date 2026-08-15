"use client";

/** 下部タブ「お知らせ」。10秒ごとにポーリングする（画面③と同じ間隔）。 */

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { EmptyState, Skeleton } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";
import { toMessage } from "@/lib/api/errorMessages";
import {
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
} from "@/lib/api/notifications";
import { formatRelative } from "@/lib/datetime";
import { getPageCache, setPageCache } from "@/lib/pageCache";
import type { NotificationItem, NotificationType } from "@/types/api";

const POLL_INTERVAL_MS = 10_000;
const NOTIFICATIONS_PER_PAGE = 10;

const NOTIFICATIONS_CACHE_KEY = "notifications";

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

/** 通知を開いたとき、その内容を確認・操作できる画面へ遷移する。 */
function routeFor(notification: NotificationItem): string | null {
  if (!notification.taskId) return null;
  switch (notification.type) {
    case "task_needs_info":
    case "task_rejected":
      return `/requests/new/review?taskId=${notification.taskId}`;
    case "task_completed":
      return `/requests/${notification.taskId}/results`;
    // 提出系は対象の提出IDがないと検品結果を表示できない。
    // 古いデータなどでIDがない場合だけ、受注詳細へフォールバックする。
    case "submission_approved":
    case "submission_retake":
    case "submission_failed":
      return notification.submissionId
        ? `/jobs/${notification.taskId}/status?submissionId=${notification.submissionId}`
        : `/jobs/${notification.taskId}`;
    default:
      return `/requests/${notification.taskId}`;
  }
}

export default function NotificationsPage() {
  const router = useRouter();
  const toast = useToast();
  const [notifications, setNotifications] = useState<NotificationItem[] | null>(() =>
    getPageCache<NotificationItem[]>(NOTIFICATIONS_CACHE_KEY) ?? null,
  );
  const [currentPage, setCurrentPage] = useState(1);

  const load = useCallback(
    async (options: { silent?: boolean } = {}) => {
      try {
        const { notifications: items } = await listNotifications();
        setNotifications(items);
      } catch (cause) {
        if (!options.silent) toast.error(toMessage(cause));
      }
    },
    [toast],
  );

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load({ silent: true }), POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [load]);

  useEffect(() => {
    if (notifications) setPageCache(NOTIFICATIONS_CACHE_KEY, notifications);
  }, [notifications]);

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
    </div>
  );
}
