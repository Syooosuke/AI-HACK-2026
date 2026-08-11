"use client";

/** 新規登録画面。登録と同時にログイン状態になり、そのままホームへ遷移する。 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button, Card } from "@/components/ui";
import { signup } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";
import { toMessage } from "@/lib/api/errorMessages";
import { saveSession } from "@/lib/session";

/** バックエンドの制約（app/schemas/auth.py）と揃える。 */
const LOGIN_ID_PATTERN = /^[A-Za-z0-9_]+$/;
const LOGIN_ID_MIN_LENGTH = 3;
const LOGIN_ID_MAX_LENGTH = 32;
const PASSWORD_MIN_LENGTH = 8;

export default function SignupPage() {
  const router = useRouter();
  const [loginId, setLoginId] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const loginIdError =
    loginId.length === 0
      ? null
      : loginId.length < LOGIN_ID_MIN_LENGTH || loginId.length > LOGIN_ID_MAX_LENGTH
        ? `ログインIDは${LOGIN_ID_MIN_LENGTH}〜${LOGIN_ID_MAX_LENGTH}文字で入力してください。`
        : !LOGIN_ID_PATTERN.test(loginId)
          ? "ログインIDは半角英数字とアンダースコアのみ使えます。"
          : null;
  const passwordError =
    password.length === 0 || password.length >= PASSWORD_MIN_LENGTH
      ? null
      : `パスワードは${PASSWORD_MIN_LENGTH}文字以上で入力してください。`;

  const canSubmit =
    loginId.length > 0 &&
    password.length > 0 &&
    displayName.trim().length > 0 &&
    !loginIdError &&
    !passwordError &&
    !pending;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!canSubmit) return;
    setPending(true);
    setError(null);
    try {
      const { token, user } = await signup({
        loginId,
        password,
        displayName: displayName.trim(),
      });
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
    <div className="space-y-6 pt-10 md:pt-0">
      <header className="text-center">
        <h1 className="text-2xl font-bold text-slate-800">新規登録</h1>
        <p className="mt-1 text-xs text-slate-500">
          1つのアカウントで「依頼する」「撮影する」の両方ができます
        </p>
      </header>

      <Card>
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
            {loginIdError ? (
              <span className="mt-1 block text-xs text-red-600">{loginIdError}</span>
            ) : (
              <span className="mt-1 block text-xs text-slate-400">
                半角英数字とアンダースコア、{LOGIN_ID_MIN_LENGTH}〜{LOGIN_ID_MAX_LENGTH}文字
              </span>
            )}
          </label>

          <label className="block">
            <span className="mb-1 block text-xs font-bold text-slate-500">パスワード</span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="new-password"
              placeholder="••••••••"
              className="w-full rounded-xl border border-slate-300 px-3 py-2.5"
            />
            {passwordError ? (
              <span className="mt-1 block text-xs text-red-600">{passwordError}</span>
            ) : (
              <span className="mt-1 block text-xs text-slate-400">
                {PASSWORD_MIN_LENGTH}文字以上
              </span>
            )}
          </label>

          <label className="block">
            <span className="mb-1 block text-xs font-bold text-slate-500">表示名</span>
            <input
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              maxLength={40}
              placeholder="山田 太郎 / 株式会社サンプル"
              className="w-full rounded-xl border border-slate-300 px-3 py-2.5"
            />
            <span className="mt-1 block text-xs text-slate-400">
              依頼や受注の相手に表示される名前です
            </span>
          </label>

          {error && (
            <p className="rounded-xl bg-red-50 px-3 py-2 text-xs text-red-700" role="alert">
              {error}
            </p>
          )}

          <Button type="submit" accent="client" loading={pending} disabled={!canSubmit}>
            登録してはじめる
          </Button>
        </form>
      </Card>

      <p className="text-center text-xs text-slate-500">
        すでにアカウントをお持ちの場合は{" "}
        <Link href="/login" className="font-bold text-client underline">
          ログイン
        </Link>
      </p>
    </div>
  );
}
