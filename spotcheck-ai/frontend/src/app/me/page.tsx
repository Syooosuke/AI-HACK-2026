"use client";

/** 下部タブ「マイページ」。プロフィールと、自分の依頼／受注への入口、ログアウト。 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Card, InfoRow, Skeleton } from "@/components/ui";
import { clearSession, getCurrentUser, subscribeSession } from "@/lib/session";
import type { AuthUser } from "@/types/api";

const LINKS = [
  { href: "/requests", label: "出した依頼", icon: "📋", hint: "審査状況・結果の確認" },
  { href: "/jobs", label: "受注した依頼", icon: "📸", hint: "撮影・提出の進行状況" },
];

export default function MyPage() {
  const router = useRouter();
  const [user, setUser] = useState<AuthUser | null | undefined>(undefined);

  useEffect(() => {
    const sync = () => setUser(getCurrentUser());
    sync();
    return subscribeSession(sync);
  }, []);

  const logout = () => {
    clearSession();
    router.replace("/login");
  };

  if (user === undefined) return <Skeleton className="h-32" />;

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold text-slate-800">マイページ</h1>

      <Card>
        {user ? (
          <>
            <InfoRow label="表示名" value={user.displayName} />
            <InfoRow label="ログインID" value={user.loginId} />
            <InfoRow label="信頼度スコア" value={`${user.trustScore.toFixed(1)} / 100`} />
            <InfoRow label="完了した依頼" value={`${user.completedTaskCount}件`} />
          </>
        ) : (
          <p className="text-sm text-slate-500">ログイン情報を取得できませんでした。</p>
        )}
      </Card>

      <ul className="space-y-2">
        {LINKS.map((link) => (
          <li key={link.href}>
            <Link
              href={link.href}
              className="flex items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-3.5 shadow-sm hover:bg-slate-50"
            >
              <span className="flex items-center gap-3">
                <span aria-hidden className="text-lg">
                  {link.icon}
                </span>
                <span>
                  <span className="block text-sm font-bold text-slate-800">{link.label}</span>
                  <span className="block text-xs text-slate-500">{link.hint}</span>
                </span>
              </span>
              <span className="text-slate-300">›</span>
            </Link>
          </li>
        ))}
      </ul>

      <button
        type="button"
        onClick={logout}
        className="w-full rounded-xl border border-slate-300 bg-white py-3 text-sm font-bold text-slate-600 hover:bg-slate-50"
      >
        ログアウト
      </button>
    </div>
  );
}
