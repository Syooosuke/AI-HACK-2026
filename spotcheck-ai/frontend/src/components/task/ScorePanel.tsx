/** スコアのゲージ＋チェック項目リスト（画面②⑦で共用）。 */

import { CheckIcon } from "@/components/ui";
import { TrustGauge } from "@/components/ui/TrustGauge";

export type ScoreCheckItem = {
  label: string;
  /** null は「判定中」。画面⑦でスピナー表示に使う。 */
  ok: boolean | null;
};

export function ScorePanel({
  score,
  items,
  label = "スコア",
  caption,
}: {
  score: number | null;
  items: ScoreCheckItem[];
  /** 読み上げ用の見出し（何のスコアか）。 */
  label?: string;
  caption?: string;
}) {
  return (
    <div className="space-y-4">
      <div className="flex justify-center">
        <TrustGauge score={score} label={label} size="lg" />
      </div>
      {caption && <p className="text-center text-xs text-slate-500">{caption}</p>}
      <ul className="divide-y divide-slate-100">
        {items.map((item) => (
          <li key={item.label} className="flex items-center justify-between py-2.5 text-sm">
            <span className="text-slate-700">{item.label}</span>
            {item.ok === null ? (
              <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-slate-200 border-t-ai" />
            ) : (
              <CheckIcon ok={item.ok} />
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
