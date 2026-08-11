"use client";

/** ログイン画面。ログインID＋パスワードで認証し、成功したらホームへ遷移する。 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button, Card } from "@/components/ui";
import { login } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";
import { toMessage } from "@/lib/api/errorMessages";
import { getToken, saveSession } from "@/lib/session";

export default function LoginPage() {
  const router = useRouter();
  const [loginId, setLoginId] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  // すでにログイン済みならホームへ
  useEffect(() => {
    if (getToken()) router.replace("/home");
  }, [router]);

  const canSubmit = loginId.trim().length > 0 && password.length > 0 && !pending;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!canSubmit) return;
    setPending(true);
    setError(null);
    try {
      const { token, user } = await login({ loginId: loginId.trim(), password });
      saveSession(token, user);
      router.replace("/home");
    } catch (cause) {
      if (cause instanceof ApiError && cause.code === "NETWORK_ERROR") {
        setError(
          "バックエンドに接続できません。`cd backend && uvicorn app.main:app --reload --port 8000` を起動してください。",
        );
      } else {
        setError(toMessage(cause));
      }
      setPending(false);
    }
  };

  return (
    <div className="space-y-6 pt-10">
      <header className="text-center">
        <h1 className="text-2xl font-bold text-slate-800">SpotCheck AI</h1>
        <p className="mt-1 text-xs text-slate-500">現地の「いま」をAIが検品して届ける</p>
      </header>

      <Card className="space-y-4">
        <form onSubmit={submit} className="space-y-4">
          <label className="block">
            <span className="mb-1 block text-xs font-bold text-slate-500">ログインID</span>
            <input
              type="text"
              value={loginId}
              onChange={(e) => setLoginId(e.target.value)}
              autoComplete="username"
              autoCapitalize="none"
              placeholder="yamada"
              className="w-full rounded-xl border border-slate-300 px-3 py-2.5"
            />
          </label>

          <label className="block">
            <span className="mb-1 block text-xs font-bold text-slate-500">パスワード</span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              placeholder="••••••••"
              className="w-full rounded-xl border border-slate-300 px-3 py-2.5"
            />
          </label>

          {error && (
            <p className="rounded-xl bg-red-50 px-3 py-2 text-xs text-red-700" role="alert">
              {error}
            </p>
          )}

          <Button type="submit" accent="client" loading={pending} disabled={!canSubmit}>
            ログイン
          </Button>
        </form>
      </Card>

      <p className="text-center text-xs text-slate-500">
        アカウントをお持ちでない場合は{" "}
        <Link href="/signup" className="font-bold text-client underline">
          新規登録
        </Link>
      </p>
    </div>
  );
}
