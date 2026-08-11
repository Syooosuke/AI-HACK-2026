"use client";

/**
 * 認証ガード。トークンが無ければログイン画面へ送る。
 * トークンがある場合は `GET /api/auth/me` で有効性を確認し、ユーザー情報を最新化する
 * （401 のときは `lib/api/client.ts` がセッションを破棄するため、ここでログインへ戻す）。
 */

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { Spinner } from "@/components/ui";
import { fetchMe } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";
import { clearSession, getToken, saveUser, subscribeSession } from "@/lib/session";

/** ログイン不要で開ける画面。 */
const PUBLIC_PATHS = ["/login", "/signup"];

export function isPublicPath(pathname: string | null): boolean {
  if (!pathname) return false;
  return PUBLIC_PATHS.includes(pathname);
}

export function AuthGuard({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const isPublic = isPublicPath(pathname);
  // ログイン・新規登録画面は判定を待たずに描画する（初回表示でスピナーを見せない）
  const [checked, setChecked] = useState(isPublic);

  useEffect(() => {
    if (isPublic) {
      setChecked(true);
      return;
    }
    if (!getToken()) {
      router.replace("/login");
      return;
    }

    let cancelled = false;
    setChecked(true); // トークンがある間は画面を出したまま裏で検証する
    void fetchMe()
      .then(({ user }) => {
        if (!cancelled) saveUser(user);
      })
      .catch((cause: unknown) => {
        if (cancelled) return;
        // 通信不能はログアウトさせない（オフライン時に締め出さないため）
        if (cause instanceof ApiError && cause.status === 401) {
          clearSession();
          router.replace("/login");
        }
      });

    return () => {
      cancelled = true;
    };
  }, [isPublic, pathname, router]);

  // 別タブでのログアウトにも追従する
  useEffect(() => {
    if (isPublic) return;
    return subscribeSession(() => {
      if (!getToken()) router.replace("/login");
    });
  }, [isPublic, router]);

  if (!checked) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <Spinner className="h-6 w-6" />
      </div>
    );
  }

  return <>{children}</>;
}
