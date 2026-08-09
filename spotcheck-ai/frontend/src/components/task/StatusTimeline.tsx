/** 進行状況タイムライン（画面③）。done は青丸＋日時、current は青枠、pending は灰丸。 */

import { formatDateTime } from "@/lib/datetime";
import type { TimelineStep } from "@/types/api";

export function StatusTimeline({ steps }: { steps: TimelineStep[] }) {
  return (
    <ol className="relative space-y-0">
      {steps.map((step, index) => {
        const isLast = index === steps.length - 1;
        return (
          <li key={step.step} className="relative flex gap-3 pb-5 last:pb-0">
            {!isLast && (
              <span
                aria-hidden
                className={`absolute left-[7px] top-4 h-full w-0.5 ${
                  step.status === "done" ? "bg-client" : "bg-slate-200"
                }`}
              />
            )}
            <span
              aria-hidden
              className={`relative z-10 mt-1 h-4 w-4 shrink-0 rounded-full border-2 ${
                step.status === "done"
                  ? "border-client bg-client"
                  : step.status === "current"
                    ? "border-client bg-white"
                    : "border-slate-300 bg-slate-100"
              }`}
            />
            <div className="min-w-0 flex-1">
              <p
                className={`text-sm ${
                  step.status === "pending" ? "text-slate-400" : "font-medium text-slate-800"
                }`}
              >
                {step.label}
                {step.status === "current" && (
                  <span className="ml-2 text-xs font-bold text-client">進行中</span>
                )}
              </p>
              {step.at && <p className="text-xs text-slate-400">{formatDateTime(step.at)}</p>}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
