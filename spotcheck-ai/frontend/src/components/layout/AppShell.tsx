"use client";

/**
 * 共通シェル。
 * - ログイン後は全員が同じ画面構成を使う（クライアント／ワーカーの区別なし）
 * - 下部タブ: ホーム / いいね / 依頼する（中央） / お知らせ / マイページ
 * - 撮影画面は全画面カメラのため、シェルを外して children だけを描画する
 * - ログイン・新規登録画面ではヘッダーとタブを出さない
 */

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { isPublicPath } from "@/components/auth/AuthGuard";
import { getCurrentUser, subscribeSession } from "@/lib/session";
import type { AuthUser } from "@/types/api";

type Tab = {
  href: string;
  label: string;
  icon: string;
  /** 中央の目立つボタン（依頼する）。 */
  primary?: boolean;
};

const TABS: Tab[] = [
  { href: "/home", label: "ホーム", icon: "🏠" },
  { href: "/likes", label: "いいね", icon: "❤️" },
  { href: "/requests/new", label: "依頼する", icon: "📸", primary: true },
  { href: "/notifications", label: "お知らせ", icon: "🔔" },
  { href: "/me", label: "マイページ", icon: "👤" },
];

/** 戻るボタンを出さない画面（タブの着地点）。 */
const TAB_ROOTS = TABS.map((tab) => tab.href);

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<AuthUser | null>(null);

  useEffect(() => {
    const sync = () => setUser(getCurrentUser());
    sync();
    return subscribeSession(sync);
  }, []);

  const isCapture = pathname?.endsWith("/capture") ?? false;
  const isAuthPage = isPublicPath(pathname);
  const isTabRoot = pathname ? TAB_ROOTS.includes(pathname) : false;

  if (isCapture) {
    return <>{children}</>;
  }

  if (isAuthPage) {
    return <div className="mx-auto flex min-h-screen max-w-app flex-col px-4">{children}</div>;
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-app flex-col">
      <header className="sticky top-0 z-30 flex items-center justify-between gap-3 border-b border-slate-200 bg-white/95 px-4 py-3 backdrop-blur">
        <div className="flex items-center gap-2">
          {!isTabRoot && (
            <button
              type="button"
              onClick={() => router.back()}
              aria-label="戻る"
              className="rounded-lg px-2 py-1 text-lg text-slate-400 hover:bg-slate-100"
            >
              ←
            </button>
          )}
          <Link href="/home" className="text-sm font-bold text-slate-800">
            SpotCheck AI
          </Link>
        </div>
        <Link
          href="/me"
          className="flex items-center gap-2 rounded-full border border-slate-200 px-3 py-1.5 text-xs font-bold text-slate-600 hover:bg-slate-50"
        >
          <span className="max-w-[8rem] truncate">{user?.displayName ?? "ゲスト"}</span>
        </Link>
      </header>

      <main className="flex-1 px-4 py-5 pb-24">{children}</main>

      <nav className="fixed inset-x-0 bottom-0 z-30 mx-auto flex max-w-app border-t border-slate-200 bg-white">
        {TABS.map((tab) => {
          const active = pathname === tab.href || pathname?.startsWith(`${tab.href}/`);
          if (tab.primary) {
            return (
              <Link
                key={tab.href}
                href={tab.href}
                className="flex flex-1 flex-col items-center gap-0.5 py-2 text-[10px] font-bold text-client"
              >
                <span
                  aria-hidden
                  className="flex h-9 w-9 items-center justify-center rounded-full bg-client text-lg leading-none text-white shadow-sm"
                >
                  {tab.icon}
                </span>
                {tab.label}
              </Link>
            );
          }
          return (
            <Link
              key={tab.href}
              href={tab.href}
              className={`flex flex-1 flex-col items-center gap-0.5 py-2.5 text-[10px] font-bold ${
                active ? "text-client" : "text-slate-400"
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
    </div>
  );
}
