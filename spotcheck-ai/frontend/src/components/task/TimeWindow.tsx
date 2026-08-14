/**
 * 撮影希望の時間帯を「幅」として見せる表示。
 *
 * 撮影は分単位で狙って行けるものではないので、**一点の日時ではなく幅**で伝える。
 * 開始と終了を波線でつなぎ、「この間に撮ってくれればよい」ことを図として示す。
 *
 * 値そのものは既存の `scheduledAt`（希望日時）と `deadlineAt`（提出期限）を使う。
 */

import { formatDateTime, formatRemaining } from "@/lib/datetime";

/** 波線。SVGのパスで、繰り返しの波を描く。 */
function WavyLine({ className = "" }: { className?: string }) {
  return (
    <svg
      aria-hidden
      viewBox="0 0 120 8"
      preserveAspectRatio="none"
      className={`h-2 w-full ${className}`}
    >
      <path
        d="M0 4 Q 5 0, 10 4 T 20 4 T 30 4 T 40 4 T 50 4 T 60 4 T 70 4 T 80 4 T 90 4 T 100 4 T 110 4 T 120 4"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

/** 見出しと補足の文言。誰に向けた画面かで言い回しを変える。 */
const WORDING = {
  worker: {
    title: "撮影してほしい時間帯",
    caption: "この幅のなかで撮影してください。",
  },
  client: {
    title: "撮影してもらう時間帯",
    caption: "この幅のなかで撮影されます。",
  },
} as const;

export function TimeWindow({
  from,
  to,
  /** 期限までの残り時間を添えるか（ワーカー向けの画面で使う） */
  showRemaining = false,
  /** 文言の向き先。既定はワーカー向け */
  audience = "worker",
}: {
  from: string;
  to: string;
  showRemaining?: boolean;
  audience?: keyof typeof WORDING;
}) {
  const wording = WORDING[audience];

  return (
    <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3">
      <p className="mb-2 flex items-center gap-2 text-xs font-bold text-slate-500">
        <span aria-hidden>🕒</span>
        {wording.title}
      </p>

      <div className="flex items-center gap-2">
        <span className="shrink-0 text-sm font-bold tabular-nums text-slate-800">
          {formatDateTime(from)}
        </span>
        <span className="min-w-0 flex-1 text-slate-300">
          <WavyLine />
        </span>
        <span className="shrink-0 text-sm font-bold tabular-nums text-slate-800">
          {formatDateTime(to)}
        </span>
      </div>

      <p className="mt-2 text-[11px] text-slate-500">
        {wording.caption}
        {showRemaining && <span className="ml-1 font-bold text-slate-600">{formatRemaining(to)}</span>}
      </p>
    </div>
  );
}
