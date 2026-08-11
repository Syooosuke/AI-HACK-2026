"use client";

/**
 * ルート。ログイン済みならホーム（撮影依頼一覧）、未ログインならログイン画面へ送る。
 * 全員が同じホームに着地し、下部タブから「依頼する」「マイページ」へ移動する。
 */

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { Spinner } from "@/components/ui";
import { getToken } from "@/lib/session";

export default function RootPage() {
  const router = useRouter();

  useEffect(() => {
    router.replace(getToken() ? "/home" : "/login");
  }, [router]);

  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <Spinner className="h-6 w-6" />
    </div>
  );
}
