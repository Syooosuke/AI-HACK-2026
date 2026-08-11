"use client";

/**
 * 公開プロフィール（閲覧専用 / docs/05-frontend.md 画面⑪）。
 *
 * ロールに依存しない。1アカウントが依頼者とワーカーの両面を持ちうるため、
 * 実績が0の側も見出しを出し「まだ実績がありません」と表示する。
 * 編集機能は持たない（編集は各自のマイページで行う）。
 */

import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { Card, EmptyState, InfoRow, SectionTitle, Skeleton } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";
import { toMessage } from "@/lib/api/errorMessages";
import { getPublicProfile } from "@/lib/api/profile";
import type { PublicProfile } from "@/types/api";

const JOINED_FORMAT = new Intl.DateTimeFormat("ja-JP", {
  year: "numeric",
  month: "long",
  timeZone: "Asia/Tokyo",
});

export default function PublicProfilePage() {
  const { userId } = useParams<{ userId: string }>();
  const toast = useToast();
  const [profile, setProfile] = useState<PublicProfile | null | undefined>(undefined);

  const load = useCallback(async () => {
    try {
      setProfile(await getPublicProfile(userId));
    } catch (cause) {
      setProfile(null);
      toast.error(toMessage(cause));
    }
  }, [userId, toast]);

  useEffect(() => {
    void load();
  }, [load]);

  if (profile === undefined) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-24" />
        <Skeleton className="h-32" />
        <Skeleton className="h-32" />
      </div>
    );
  }

  if (profile === null) {
    return <EmptyState message="このユーザーのプロフィールを表示できませんでした。" />;
  }

  const { asRequester, asWorker } = profile;
  const hasRequesterHistory = asRequester.publishedTaskCount > 0;
  const hasWorkerHistory = asWorker.approvedSubmissionCount > 0;

  return (
    <div className="space-y-5">
      <Card className="flex items-center gap-4">
        <span className="flex h-14 w-14 shrink-0 items-center justify-center overflow-hidden rounded-full bg-slate-100 text-2xl">
          {profile.avatarUrl ? (
            // next/image は任意ホストの画像を許可設定なしに扱えないため img を使う
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={profile.avatarUrl}
              alt=""
              className="h-full w-full object-cover"
            />
          ) : (
            "👤"
          )}
        </span>
        <div className="min-w-0">
          <h1 className="truncate text-lg font-bold text-slate-800">{profile.displayName}</h1>
          <p className="text-xs text-slate-500">
            {JOINED_FORMAT.format(new Date(profile.joinedAt))}から利用
          </p>
        </div>
      </Card>

      <Card>
        <SectionTitle>依頼者としての実績</SectionTitle>
        {hasRequesterHistory ? (
          <>
            <InfoRow label="公開した依頼" value={`${asRequester.publishedTaskCount}件`} />
            <InfoRow label="完了した依頼" value={`${asRequester.completedTaskCount}件`} />
            <InfoRow
              label="完了率"
              value={
                asRequester.completionRate == null
                  ? "—"
                  : `${Math.round(asRequester.completionRate * 100)}%`
              }
            />
          </>
        ) : (
          <p className="py-2 text-sm text-slate-500">まだ依頼の実績がありません。</p>
        )}
      </Card>

      <Card>
        <SectionTitle>ワーカーとしての実績</SectionTitle>
        {hasWorkerHistory ? (
          <>
            <InfoRow
              label="信頼度"
              value={
                <span className="text-amber-500">
                  {"★".repeat(Math.round(asWorker.trustScore)).padEnd(5, "☆")}
                  <span className="ml-1 text-xs text-slate-500">
                    {asWorker.trustScore.toFixed(1)}
                  </span>
                </span>
              }
            />
            <InfoRow label="合格した提出" value={`${asWorker.approvedSubmissionCount}件`} />
          </>
        ) : (
          <p className="py-2 text-sm text-slate-500">まだ撮影の実績がありません。</p>
        )}
      </Card>

      <p className="text-center text-[10px] text-slate-400">
        このページは閲覧専用です。連絡先などの個人情報は表示されません。
      </p>
    </div>
  );
}
