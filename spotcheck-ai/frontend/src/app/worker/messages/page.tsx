/** 下部タブ「メッセージ」。デモ範囲外のためプレースホルダ（docs/05-frontend.md 1節）。 */

import { EmptyState } from "@/components/ui";

export default function MessagesPage() {
  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold text-slate-800">メッセージ</h1>
      <EmptyState message="メッセージ機能はデモ範囲外です。" />
    </div>
  );
}
