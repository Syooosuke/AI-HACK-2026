"use client";

/**
 * 共通シェル（docs/05-frontend.md 1節・2節）。
 * - ヘッダー右上に現在のデモユーザーを表示し、タップでトップの切替画面へ戻す
 * - ワーカー側のみ下部固定タブバーを表示する
 * - 画面⑥（撮影）は全画面カメラのため、シェルを外して children だけを描画する
 */

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { getDemoUser, subscribeDemoUser } from "@/lib/demoUser";
import type { DemoUser } from "@/types/api";

const WORKER_TABS = [
  { href: "/worker/tasks", label: "ホーム", icon: "🏠" },
  { href: "/worker/assignments", label: "依頼", icon: "📋" },
  { href: "/worker/messages", label: "メッセージ", icon: "💬" },
  { href: "/worker/me", label: "マイページ", icon: "👤" },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<DemoUser | null>(null);

  useEffect(() => {
    const sync = () => setUser(getDemoUser());
    sync();
    return subscribeDemoUser(sync);
  }, []);

  const isCapture = pathname?.endsWith("/capture") ?? false;
  const isWorker = pathname?.startsWith("/worker") ?? false;
  const isTop = pathname === "/";

  if (isCapture) {
    return <>{children}</>;
  }

  const accent = isWorker ? "text-worker" : "text-client";

  return (
    <div className="mx-auto flex min-h-screen max-w-app flex-col">
      {!isTop && (
        <header className="sticky top-0 z-30 flex items-center justify-between gap-3 border-b border-slate-200 bg-white/95 px-4 py-3 backdrop-blur">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => router.back()}
              aria-label="戻る"
              className="rounded-lg px-2 py-1 text-lg text-slate-400 hover:bg-slate-100"
            >
              ←
            </button>
            <Link href={isWorker ? "/worker/tasks" : "/client/tasks"} className="leading-tight">
              <span className="block text-sm font-bold text-slate-800">SpotCheck AI</span>
              <span className={`block text-[10px] font-bold ${accent}`}>
                {isWorker ? "ワーカー" : "クライアント"}
              </span>
            </Link>
          </div>
          <Link
            href="/"
            className="flex items-center gap-2 rounded-full border border-slate-200 px-3 py-1.5 text-xs font-bold text-slate-600 hover:bg-slate-50"
          >
            <span className="max-w-[8rem] truncate">{user?.displayName ?? "未選択"}</span>
            <span className="text-slate-400">切替</span>
          </Link>
        </header>
      )}

      <main className={`flex-1 px-4 py-5 ${isWorker ? "pb-24" : "pb-10"}`}>{children}</main>

      {isWorker && (
        <nav className="fixed inset-x-0 bottom-0 z-30 mx-auto flex max-w-app border-t border-slate-200 bg-white">
          {WORKER_TABS.map((tab) => {
            const active = pathname?.startsWith(tab.href) ?? false;
            return (
              <Link
                key={tab.href}
                href={tab.href}
                className={`flex flex-1 flex-col items-center gap-0.5 py-2.5 text-[10px] font-bold ${
                  active ? "text-worker" : "text-slate-400"
                }`}
              >
                <span aria-hidden className="text-lg leading-none">
                  {tab.icon}
                </span>
                {tab.label}
              </Link>
            );
          })}
        </nav>
      )}
    </div>
  );
}
