/** 下部タブ「お知らせ」。通知機能はデモ範囲外のためプレースホルダ。 */

import { EmptyState } from "@/components/ui";

export default function NotificationsPage() {
  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold text-slate-800">お知らせ</h1>
      <EmptyState message="お知らせはまだありません。検品結果は「マイページ」から確認できます。" />
    </div>
  );
}
