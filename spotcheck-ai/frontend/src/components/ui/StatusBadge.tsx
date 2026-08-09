/** ステータス→ラベル/色のマッピングを内包するバッジ（docs/05-frontend.md 1節）。 */

import type { AssignmentStatus, TaskStatus, ValidationStatus } from "@/types/api";

type Tone = "amber" | "red" | "blue" | "emerald" | "slate" | "violet";

const TONE_CLASS: Record<Tone, string> = {
  amber: "bg-amber-50 text-amber-700 border-amber-200",
  red: "bg-red-50 text-red-700 border-red-200",
  blue: "bg-blue-50 text-blue-700 border-blue-200",
  emerald: "bg-emerald-50 text-emerald-700 border-emerald-200",
  slate: "bg-slate-100 text-slate-600 border-slate-200",
  violet: "bg-violet-50 text-violet-700 border-violet-200",
};

const TASK_STATUS: Record<TaskStatus, { label: string; tone: Tone }> = {
  screening: { label: "審査中", tone: "amber" },
  needs_info: { label: "情報補足待ち", tone: "amber" },
  rejected: { label: "却下", tone: "red" },
  open: { label: "募集中", tone: "blue" },
  in_progress: { label: "進行中", tone: "blue" },
  completed: { label: "完了", tone: "emerald" },
  expired: { label: "期限切れ", tone: "slate" },
  cancelled: { label: "取消済み", tone: "slate" },
};

const ASSIGNMENT_STATUS: Record<AssignmentStatus, { label: string; tone: Tone }> = {
  accepted: { label: "受注中", tone: "blue" },
  submitted: { label: "検品中", tone: "violet" },
  approved: { label: "合格", tone: "emerald" },
  failed: { label: "不成立", tone: "red" },
  cancelled: { label: "取消済み", tone: "slate" },
  expired: { label: "期限切れ", tone: "slate" },
};

const VALIDATION_STATUS: Record<ValidationStatus, { label: string; tone: Tone }> = {
  pending: { label: "検品待ち", tone: "amber" },
  processing: { label: "検品中", tone: "violet" },
  approved: { label: "合格", tone: "emerald" },
  rejected: { label: "再撮影が必要", tone: "red" },
  error: { label: "検品エラー", tone: "slate" },
};

function Badge({ label, tone }: { label: string; tone: Tone }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-bold ${TONE_CLASS[tone]}`}
    >
      {label}
    </span>
  );
}

export function StatusBadge({ status }: { status: TaskStatus }) {
  return <Badge {...TASK_STATUS[status]} />;
}

export function AssignmentBadge({ status }: { status: AssignmentStatus }) {
  return <Badge {...ASSIGNMENT_STATUS[status]} />;
}

export function ValidationBadge({ status }: { status: ValidationStatus }) {
  return <Badge {...VALIDATION_STATUS[status]} />;
}

export function taskStatusLabel(status: TaskStatus): string {
  return TASK_STATUS[status].label;
}
