/**
 * 星評価の表示。
 *
 * 星は**依頼者が人手で付ける5段階の評価**で、システムが自動計算する
 * 「信頼度スコア」とは別物。混同しないよう、画面では役割を書き分ける。
 */

import type { WorkerReviewTag } from "@/types/api";

/** 評価タグの日本語表記。評価を出す画面と見る画面で同じ語を使う。 */
export const REVIEW_TAG_LABELS: Record<WorkerReviewTag, string> = {
  as_requested: "依頼どおり",
  clear_photo: "写真が見やすい",
  fast_response: "対応が早い",
  accurate_location: "位置情報が正確",
};

export function Stars({
  value,
  size = "md",
}: {
  /** 0〜5。小数は四捨五入せず、半分以上なら半分の星として扱う */
  value: number;
  size?: "sm" | "md" | "lg";
}) {
  const textSize = size === "lg" ? "text-xl" : size === "sm" ? "text-xs" : "text-sm";
  return (
    <span className={`inline-flex items-center ${textSize} leading-none tracking-tight`}>
      {[1, 2, 3, 4, 5].map((position) => {
        const filled = value >= position - 0.25;
        const half = !filled && value >= position - 0.75;
        return (
          <span
            key={position}
            aria-hidden
            className={filled || half ? "text-amber-400" : "text-slate-300"}
          >
            {filled ? "★" : half ? "★" : "☆"}
          </span>
        );
      })}
      <span className="sr-only">5段階中 {value.toFixed(1)}</span>
    </span>
  );
}
