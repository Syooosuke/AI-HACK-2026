"use client";

/**
 * 共通シェル。ログイン後は全員が同じ画面構成を使う（クライアント／ワーカーの区別なし）。
 *
 * **モバイルとPCで導線の置き方だけを変える。**
 * - モバイル（〜md）: 画面下部に固定タブバー（ホーム / いいね / 依頼する / お知らせ / マイページ）
 * - PC（md〜）: 左に固定サイドナビ。下部タブは隠し、本文の最大幅を広げる
 * - 撮影画面は全画面カメラのため、シェルを外して children だけを描画する
 * - ログイン・新規登録画面ではナビを出さない
 */

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { isPublicPath } from "@/components/auth/AuthGuard";
import { Avatar } from "@/components/ui/Avatar";
import { getUnreadNotificationCount } from "@/lib/api/notifications";
import { getCurrentUser, subscribeSession } from "@/lib/session";
import type { AuthUser } from "@/types/api";

/** お知らせタブの未読バッジをポーリングする間隔。一覧画面ほど鮮度は要らないため長め。 */
const UNREAD_POLL_INTERVAL_MS = 30_000;

type Tab = {
  href: string;
  label: string;
  icon: string;
  /** 目立たせる導線（依頼する）。モバイルは中央の丸ボタン、PCは塗りボタン。 */
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

function isActive(pathname: string | null, href: string): boolean {
  if (!pathname) return false;
  return pathname === href || pathname.startsWith(`${href}/`);
}

/** タブアイコン右上の未読件数バッジ。0件なら何も出さない。 */
function TabBadge({ count }: { count: number }) {
  if (count <= 0) return null;
  return (
    <span
      aria-hidden
      className="absolute -right-1.5 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-fail px-1 text-[9px] font-bold leading-none text-white"
    >
      {count > 9 ? "9+" : count}
    </span>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [unreadCount, setUnreadCount] = useState(0);

  useEffect(() => {
    const sync = () => setUser(getCurrentUser());
    sync();
    return subscribeSession(sync);
  }, []);

  useEffect(() => {
    if (!user) {
      setUnreadCount(0);
      return;
    }
    let cancelled = false;
    const load = () => {
      getUnreadNotificationCount()
        .then(({ count }) => {
          if (!cancelled) setUnreadCount(count);
        })
        .catch(() => {
          // バッジは補助表示のため、失敗しても静かに無視する（既存のトースト運用を邪魔しない）
        });
    };
    load();
    const timer = window.setInterval(load, UNREAD_POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [user]);

  const isCapture = pathname?.endsWith("/capture") ?? false;
  const isAuthPage = isPublicPath(pathname);
  const isTabRoot = pathname ? TAB_ROOTS.includes(pathname) : false;

  if (isCapture) {
    return <>{children}</>;
  }

  if (isAuthPage) {
    return (
      <div className="mx-auto flex min-h-screen w-full max-w-app flex-col px-4 md:justify-center">
        {children}
      </div>
    );
  }

  return (
    <div className="min-h-screen md:flex">
      {/* PC: 左の固定サイドナビ */}
      <aside className="sticky top-0 hidden h-screen w-56 shrink-0 flex-col border-r border-slate-200 bg-white px-4 py-6 md:flex lg:w-64">
        <Link href="/home" className="mb-6 block px-2 text-base font-bold text-slate-800">
          SpotCheck AI
        </Link>
        <nav className="flex flex-1 flex-col gap-1">
          {TABS.map((tab) =>
            tab.primary ? (
              <Link
                key={tab.href}
                href={tab.href}
                className="my-2 flex items-center justify-center gap-2 rounded-xl bg-client px-3 py-2.5 text-sm font-bold text-white transition hover:bg-blue-700"
              >
                <span aria-hidden>{tab.icon}</span>
                {tab.label}
              </Link>
            ) : (
              <Link
                key={tab.href}
                href={tab.href}
                className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-bold transition ${
                  isActive(pathname, tab.href)
                    ? "bg-slate-100 text-client"
                    : "text-slate-500 hover:bg-slate-50"
                }`}
              >
                <span aria-hidden className="relative text-lg leading-none">
                  {tab.icon}
                  {tab.href === "/notifications" && <TabBadge count={unreadCount} />}
                </span>
                {tab.label}
              </Link>
            ),
          )}
        </nav>
        {user && (
          <Link
            href="/me"
            className="mt-4 flex items-center gap-2 rounded-xl border border-slate-200 px-2 py-2 text-xs font-bold text-slate-600 hover:bg-slate-50"
          >
            <Avatar name={user.displayName} src={user.avatarUrl} size="xs" />
            <span className="truncate">{user.displayName}</span>
          </Link>
        )}
      </aside>

      <div className="flex min-h-screen w-full flex-1 flex-col">
        <header className="sticky top-0 z-30 flex items-center justify-between gap-3 border-b border-slate-200 bg-white/95 px-4 py-3 backdrop-blur md:px-8">
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
            {/* PC はサイドナビにロゴがあるため出さない */}
            <Link href="/home" className="text-sm font-bold text-slate-800 md:hidden">
              SpotCheck AI
            </Link>
          </div>
          <Link
            href="/me"
            aria-label="マイページ"
            className="flex items-center gap-2 rounded-full border border-slate-200 py-1 pl-1 pr-3 text-xs font-bold text-slate-600 hover:bg-slate-50 md:hidden"
          >
            <Avatar name={user?.displayName ?? "ゲスト"} src={user?.avatarUrl} size="xs" />
            <span className="max-w-[8rem] truncate">{user?.displayName ?? "ゲスト"}</span>
          </Link>
        </header>

        <main className="mx-auto w-full max-w-app flex-1 px-4 py-5 pb-24 md:max-w-5xl md:px-8 md:pb-10">
          {children}
        </main>

        {/* モバイル: 下部タブバー */}
        <nav className="fixed inset-x-0 bottom-0 z-30 mx-auto flex max-w-app border-t border-slate-200 bg-white md:hidden">
          {TABS.map((tab) => {
            const active = isActive(pathname, tab.href);
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
                <span aria-hidden className="relative text-lg leading-none">
                  {tab.icon}
                  {tab.href === "/notifications" && <TabBadge count={unreadCount} />}
                </span>
                {tab.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </div>
  );
}
