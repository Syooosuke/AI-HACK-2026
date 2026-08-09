/** ポーリング中の表示。 */

import { Spinner } from "@/components/ui";

export function PollingIndicator({
  label = "最新の状況を確認しています",
  stopped = false,
}: {
  label?: string;
  stopped?: boolean;
}) {
  if (stopped) {
    return (
      <p className="text-center text-xs text-slate-400">
        自動更新を停止しました。画面を再読み込みすると再開します。
      </p>
    );
  }
  return (
    <p className="flex items-center justify-center gap-2 text-xs text-slate-400">
      <Spinner className="h-3 w-3" />
      {label}
    </p>
  );
}
