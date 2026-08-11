"use client";

/**
 * トップ: デモユーザー（ロール）選択（docs/05-frontend.md 2節 / D-06）。
 * 選択したIDは localStorage に保持され、全APIリクエストへ自動付与される。
 */

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { Card, Skeleton, Spinner } from "@/components/ui";
import { ApiError } from "@/lib/api/client";
import { toMessage } from "@/lib/api/errorMessages";
import { listDemoUsers } from "@/lib/api/users";
import { getDemoUser, setDemoUser } from "@/lib/demoUser";
import type { DemoUser } from "@/types/api";

export default function TopPage() {
  const router = useRouter();
  const [users, setUsers] = useState<DemoUser[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [currentId, setCurrentId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const { users: fetched } = await listDemoUsers();
      setUsers(fetched);
    } catch (cause) {
      setUsers([]);
      setError(toMessage(cause));
      if (cause instanceof ApiError && cause.code === "NETWORK_ERROR") {
        setError(
          "バックエンドに接続できません。`cd backend && uvicorn app.main:app --reload --port 8000` を起動してください。",
        );
      }
    }
  }, []);

  useEffect(() => {
    setCurrentId(getDemoUser()?.id ?? null);
    void load();
  }, [load]);

  const choose = (user: DemoUser) => {
    setDemoUser(user);
    setCurrentId(user.id);
    router.push(user.role === "client" ? "/client/tasks" : "/worker/tasks");
  };

  const clients = users?.filter((user) => user.role === "client") ?? [];
  const workers = users?.filter((user) => user.role === "worker") ?? [];

  return (
    <div className="space-y-6 pt-6">
      <header className="text-center">
        <h1 className="text-2xl font-bold text-slate-800">SpotCheck AI</h1>
      </header>

      {error && (
        <Card className="border-red-200 bg-red-50">
          <p className="text-sm text-red-700">{error}</p>
          <button
            type="button"
            onClick={() => void load()}
            className="mt-3 text-xs font-bold text-red-700 underline"
          >
            再試行する
          </button>
        </Card>
      )}

      {users === null ? (
        <div className="space-y-3">
          <Skeleton className="h-20" />
          <Skeleton className="h-20" />
        </div>
      ) : (
        <>
          <section className="space-y-2">
            <h2 className="text-sm font-bold text-client">依頼する（クライアント）</h2>
            {clients.map((user) => (
              <UserButton
                key={user.id}
                user={user}
                selected={user.id === currentId}
                onSelect={choose}
              />
            ))}
          </section>

          <section className="space-y-2">
            <h2 className="text-sm font-bold text-worker">撮影する（ワーカー）</h2>
            {workers.map((user) => (
              <UserButton
                key={user.id}
                user={user}
                selected={user.id === currentId}
                onSelect={choose}
              />
            ))}
          </section>
        </>
      )}
    </div>
  );
}

function UserButton({
  user,
  selected,
  onSelect,
}: {
  user: DemoUser;
  selected: boolean;
  onSelect: (user: DemoUser) => void;
}) {
  const [pending, setPending] = useState(false);
  const accent = user.role === "client" ? "border-client" : "border-worker";
  return (
    <button
      type="button"
      onClick={() => {
        setPending(true);
        onSelect(user);
      }}
      className={`flex w-full items-center justify-between gap-3 rounded-2xl border bg-white px-4 py-3.5 text-left shadow-sm transition hover:bg-slate-50 ${
        selected ? `${accent} ring-2 ring-slate-100` : "border-slate-200"
      }`}
    >
      <span>
        <span className="block text-sm font-bold text-slate-800">{user.displayName}</span>
        <span className="block text-xs text-slate-500">
          {user.role === "worker"
            ? `信頼度 ${user.trustScore.toFixed(1)} / 完了 ${user.completedTaskCount}件`
            : "依頼の作成・結果閲覧"}
        </span>
      </span>
      {pending ? <Spinner /> : <span className="text-slate-300">›</span>}
    </button>
  );
}
