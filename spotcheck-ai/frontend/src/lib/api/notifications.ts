/** お知らせ（画面下部タブ）のAPI。 */

import { apiFetch } from "@/lib/api/client";
import type { NotificationItem } from "@/types/api";

export function listNotifications(): Promise<{ notifications: NotificationItem[] }> {
  return apiFetch<{ notifications: NotificationItem[] }>("/api/notifications");
}

export function getUnreadNotificationCount(): Promise<{ count: number }> {
  return apiFetch<{ count: number }>("/api/notifications/unread-count");
}

export function markNotificationRead(notificationId: string): Promise<void> {
  return apiFetch<void>(`/api/notifications/${notificationId}/read`, { method: "POST" });
}

export function markAllNotificationsRead(): Promise<void> {
  return apiFetch<void>("/api/notifications/read-all", { method: "POST" });
}
