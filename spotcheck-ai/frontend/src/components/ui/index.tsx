/**
 * 共通UIコンポーネント（docs/05-frontend.md 1節・4節）。
 * カードは white + border-slate-200 + rounded-2xl + shadow-sm で統一する。
 */

import type { ButtonHTMLAttributes, ReactNode } from "react";

type Accent = "client" | "worker" | "ai" | "neutral" | "danger";

const ACCENT_CLASS: Record<Accent, string> = {
  client: "bg-client hover:bg-blue-700 text-white",
  worker: "bg-worker hover:bg-emerald-700 text-white",
  ai: "bg-ai hover:bg-violet-700 text-white",
  neutral: "bg-white border border-slate-300 text-slate-700 hover:bg-slate-50",
  danger: "bg-fail hover:bg-red-600 text-white",
};

export function Button({
  accent = "client",
  loading = false,
  children,
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  accent?: Accent;
  loading?: boolean;
}) {
  return (
    <button
      {...props}
      disabled={props.disabled || loading}
      className={`flex w-full items-center justify-center gap-2 rounded-xl px-4 py-3.5 text-sm font-bold transition disabled:cursor-not-allowed disabled:opacity-40 ${ACCENT_CLASS[accent]} ${className}`}
    >
      {loading && <Spinner className="h-4 w-4 border-white/40 border-t-white" />}
      {children}
    </button>
  );
}

export function Card({
  children,
  className = "",
  as: Tag = "div",
}: {
  children: ReactNode;
  className?: string;
  as?: "div" | "section" | "li" | "article";
}) {
  return (
    <Tag
      className={`rounded-2xl border border-slate-200 bg-white p-4 shadow-sm ${className}`}
    >
      {children}
    </Tag>
  );
}

export function Spinner({ className = "" }: { className?: string }) {
  return (
    <span
      role="status"
      aria-label="読み込み中"
      className={`inline-block animate-spin rounded-full border-2 border-slate-200 border-t-slate-500 ${className || "h-4 w-4"}`}
    />
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-lg bg-slate-200 ${className}`} />;
}

export function SectionTitle({ children }: { children: ReactNode }) {
  return <h2 className="mb-2 text-sm font-bold text-slate-500">{children}</h2>;
}

export function InfoRow({
  label,
  value,
  icon,
}: {
  label: string;
  value: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-3 py-1.5 text-sm">
      {/*
        ラベルは縮めない（shrink-0）。値が長いとラベル側が潰され、
        「撮影地点」のような短い語が1文字ずつ折り返されて縦書きに見えてしまう
      */}
      <span className="flex shrink-0 items-center gap-2 whitespace-nowrap text-slate-500">
        {icon}
        {label}
      </span>
      <span className="min-w-0 break-words text-right font-medium text-slate-800">{value}</span>
    </div>
  );
}

export function EmptyState({ message, action }: { message: string; action?: ReactNode }) {
  return (
    <div className="rounded-2xl border border-dashed border-slate-300 bg-white px-4 py-10 text-center">
      <p className="text-sm text-slate-500">{message}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function CheckIcon({ ok }: { ok: boolean }) {
  return ok ? (
    <span className="text-base font-bold text-pass" aria-label="合格">
      ✓
    </span>
  ) : (
    <span className="text-base font-bold text-fail" aria-label="不合格">
      ✗
    </span>
  );
}
