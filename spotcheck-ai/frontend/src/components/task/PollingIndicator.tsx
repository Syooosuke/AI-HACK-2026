/** ポーリング中の表示。経過時間と、待ち時間の目安を添える。 */

import { Spinner } from "@/components/ui";

export function PollingIndicator({
  label = "最新の状況を確認しています",
  /** 待ち時間の目安など、下に小さく添える説明。 */
  hint,
  stopped = false,
}: {
  label?: string;
  hint?: string;
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
    <div className="space-y-1 text-center">
      <p className="flex items-center justify-center gap-2 text-xs text-slate-400">
        <Spinner className="h-3 w-3" />
        {label}
      </p>
      {hint && <p className="px-4 text-[11px] leading-relaxed text-slate-400">{hint}</p>}
    </div>
  );
}
