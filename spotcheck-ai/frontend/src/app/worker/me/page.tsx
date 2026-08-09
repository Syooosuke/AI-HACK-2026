"use client";

/** 下部タブ「マイページ」。現在のデモユーザーの情報のみを表示する簡易版。 */

import Link from "next/link";
import { useEffect, useState } from "react";

import { Card, InfoRow, Skeleton } from "@/components/ui";
import { getDemoUser, subscribeDemoUser } from "@/lib/demoUser";
import type { DemoUser } from "@/types/api";

export default function MyPage() {
  const [user, setUser] = useState<DemoUser | null | undefined>(undefined);

  useEffect(() => {
    const sync = () => setUser(getDemoUser());
    sync();
    return subscribeDemoUser(sync);
  }, []);

  if (user === undefined) return <Skeleton className="h-32" />;

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold text-slate-800">マイページ</h1>
      <Card>
        {user ? (
          <>
            <InfoRow label="表示名" value={user.displayName} />
            <InfoRow label="信頼度スコア" value={`${user.trustScore.toFixed(1)} / 100`} />
            <InfoRow label="完了した依頼" value={`${user.completedTaskCount}件`} />
          </>
        ) : (
          <p className="text-sm text-slate-500">デモユーザーが選択されていません。</p>
        )}
      </Card>
      <Link href="/" className="block text-center text-sm font-bold text-worker underline">
        ユーザーを切り替える
      </Link>
    </div>
  );
}
