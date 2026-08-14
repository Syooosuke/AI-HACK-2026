/**
 * 撮影希望の時間帯を「幅」として見せる表示。
 *
 * 撮影は分単位で狙って行けるものではないので、**一点の日時ではなく幅**で伝える。
 * 開始と終了をタイムラインでつなぎ、「この間に撮ってくれればよい」ことを図として示す。
 *
 * 値そのものは既存の `scheduledAt`（希望日時）と `deadlineAt`（提出期限）を使う。
 */

import { formatDateTime, formatRemaining } from "@/lib/datetime";

/** 見出しと補足の文言。誰に向けた画面かで言い回しを変える。 */
const WORDING = {
  worker: {
    title: "撮影してほしい時間帯",
  },
  client: {
    title: "撮影してもらう時間帯",
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
  const isClient = audience === "client";

  return (
    <section
      className={`rounded-2xl border border-slate-200 bg-gradient-to-br shadow-sm ${
        isClient ? "from-white via-white to-blue-50/60" : "from-white via-white to-emerald-50/60"
      }`}
    >
      <div className="p-4 sm:p-5">
        <div className="flex items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2.5">
            <span
              aria-hidden
              className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-xl ${
                isClient ? "bg-blue-100/70 text-client" : "bg-emerald-100/70 text-worker"
              }`}
            >
              <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4">
                <circle cx="12" cy="12" r="8" stroke="currentColor" strokeWidth="1.8" />
                <path
                  d="M12 7.5V12l3 2"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </span>
            <span className="min-w-0">
              <span className="block text-sm font-bold text-slate-700">{wording.title}</span>
            </span>
          </div>
          {showRemaining && (
            <span
              className={`shrink-0 rounded-full border bg-white/80 px-2.5 py-1 text-[11px] font-bold shadow-sm ${
                isClient ? "border-blue-100 text-client" : "border-emerald-100 text-worker"
              }`}
            >
              {formatRemaining(to)}
            </span>
          )}
        </div>

        <div className="mt-4 grid grid-cols-[minmax(0,1fr)_2rem_minmax(0,1fr)] items-stretch gap-2 sm:grid-cols-[minmax(0,1fr)_2.5rem_minmax(0,1fr)] sm:gap-3">
          <div className="rounded-xl border border-white/80 bg-white/80 px-3 py-2.5 shadow-sm ring-1 ring-slate-100">
            <span
              className={`block text-[10px] font-bold ${isClient ? "text-client" : "text-worker"}`}
            >
              START
            </span>
            <span className="mt-1 block whitespace-nowrap text-[13px] font-bold tabular-nums text-slate-800 sm:text-base">
              {formatDateTime(from)}
            </span>
          </div>

          <div className="flex items-center justify-center" aria-hidden>
            <span
              className={`flex h-7 w-7 items-center justify-center rounded-full bg-white text-sm font-bold shadow-sm ring-1 ${
                isClient ? "text-client ring-blue-100" : "text-worker ring-emerald-100"
              }`}
            >
              →
            </span>
          </div>

          <div className="rounded-xl border border-white/80 bg-white/80 px-3 py-2.5 text-left shadow-sm ring-1 ring-slate-100">
            <span
              className={`block text-left text-[10px] font-bold ${isClient ? "text-client" : "text-worker"}`}
            >
              END
            </span>
            <span className="mt-1 block whitespace-nowrap text-left text-[13px] font-bold tabular-nums text-slate-800 sm:text-base">
              {formatDateTime(to)}
            </span>
          </div>
        </div>
      </div>
    </section>
  );
}
