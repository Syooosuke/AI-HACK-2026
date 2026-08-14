"use client";

/** 下部タブ「マイページ」。プロフィール（アイコン・信頼度）と、自分の依頼／受注への入口、ログアウト。 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { Card, InfoRow, SectionTitle, Skeleton } from "@/components/ui";
import { Avatar } from "@/components/ui/Avatar";
import { REVIEW_TAG_LABELS, Stars } from "@/components/ui/Stars";
import { TrustGauge } from "@/components/ui/TrustGauge";
import { useToast } from "@/components/ui/Toast";
import { toMessage } from "@/lib/api/errorMessages";
import { deleteAvatar, getMyReceivedReviews, uploadAvatar } from "@/lib/api/users";
import { clearSession, getCurrentUser, saveUser, subscribeSession } from "@/lib/session";
import type { AuthUser, ReceivedWorkerReviews } from "@/types/api";

const LINKS = [
  { href: "/requests", label: "出した依頼", icon: "📋", hint: "審査状況・結果の確認" },
  { href: "/jobs", label: "受注した依頼", icon: "📸", hint: "撮影・提出の進行状況" },
];

/** マイページに出す評価の件数。全件は公開プロフィールで見られる。 */
const REVIEWS_ON_MY_PAGE = 3;

/** バックエンドの ALLOWED_IMAGE_TYPES と揃える。 */
const ACCEPTED_TYPES = "image/jpeg,image/png,image/webp";

export default function MyPage() {
  const router = useRouter();
  const toast = useToast();
  const fileInput = useRef<HTMLInputElement>(null);
  const [user, setUser] = useState<AuthUser | null | undefined>(undefined);
  const [saving, setSaving] = useState(false);
  // undefined=読み込み中 / null=取得失敗
  const [reviews, setReviews] = useState<ReceivedWorkerReviews | null | undefined>(undefined);

  useEffect(() => {
    const sync = () => setUser(getCurrentUser());
    sync();
    return subscribeSession(sync);
  }, []);

  useEffect(() => {
    // 評価が取れなくてもマイページ自体は表示できるため、失敗しても握りつぶす
    getMyReceivedReviews()
      .then(setReviews)
      .catch(() => setReviews(null));
  }, []);

  const logout = () => {
    clearSession();
    router.replace("/login");
  };

  /** 画像を選び直したらすぐアップロードして、ヘッダーの表示にも反映する。 */
  const changeAvatar = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    // 同じファイルを選び直しても onChange が起きるように、入力値は毎回空へ戻す
    event.target.value = "";
    if (!file) return;

    setSaving(true);
    try {
      const result = await uploadAvatar(file);
      saveUser(result.user);
      toast.success("アイコンを変更しました。");
    } catch (cause) {
      toast.error(toMessage(cause));
    } finally {
      setSaving(false);
    }
  };

  const removeAvatar = async () => {
    setSaving(true);
    try {
      const result = await deleteAvatar();
      saveUser(result.user);
      toast.success("アイコンを既定に戻しました。");
    } catch (cause) {
      toast.error(toMessage(cause));
    } finally {
      setSaving(false);
    }
  };

  if (user === undefined) return <Skeleton className="h-32" />;

  return (
    <div className="space-y-4 md:mx-auto md:max-w-2xl">
      <h1 className="text-lg font-bold text-slate-800">マイページ</h1>

      <Card>
        {user ? (
          <>
            <div className="flex items-center gap-4">
              <div className="relative">
                <button
                  type="button"
                  onClick={() => fileInput.current?.click()}
                  disabled={saving}
                  aria-label="アイコン画像を変更する"
                  className="block rounded-full ring-2 ring-slate-100 transition hover:ring-client disabled:opacity-50"
                >
                  <Avatar name={user.displayName} src={user.avatarUrl} size="xl" />
                </button>
                <span
                  aria-hidden
                  className="pointer-events-none absolute -bottom-1 -right-1 flex h-8 w-8 items-center justify-center rounded-full border-2 border-white bg-client text-sm text-white shadow-sm"
                >
                  {saving ? "…" : "📷"}
                </span>
                <input
                  ref={fileInput}
                  type="file"
                  accept={ACCEPTED_TYPES}
                  onChange={(event) => void changeAvatar(event)}
                  className="hidden"
                />
              </div>

              <div className="min-w-0 flex-1">
                <p className="truncate text-base font-bold text-slate-800">{user.displayName}</p>
                <p className="truncate text-xs text-slate-500">@{user.loginId}</p>
                <div className="mt-2 flex gap-2">
                  <button
                    type="button"
                    onClick={() => fileInput.current?.click()}
                    disabled={saving}
                    className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-bold text-slate-600 hover:bg-slate-50 disabled:opacity-50"
                  >
                    画像を変更
                  </button>
                  {user.avatarUrl && (
                    <button
                      type="button"
                      onClick={() => void removeAvatar()}
                      disabled={saving}
                      className="rounded-lg px-3 py-1.5 text-xs font-bold text-slate-400 hover:bg-slate-50 disabled:opacity-50"
                    >
                      削除
                    </button>
                  )}
                </div>
              </div>
            </div>

            <div className="mt-4 flex items-center gap-5 border-t border-slate-100 pt-4">
              <TrustGauge score={user.trustScore} label="信頼度スコア" size="lg" />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-bold text-slate-700">信頼度スコア</p>
                <p className="mt-1 text-xs leading-relaxed text-slate-500">
                  <span className="font-bold">AIの検品結果から自動で増減する積み上げ式</span>
                  のスコアです（50点から始まり、合格で加点・失格で減点）。
                  人からの評価とは別の指標です。
                </p>
                <div className="mt-2">
                  <InfoRow label="完了した依頼" value={`${user.completedTaskCount}件`} />
                </div>
              </div>
            </div>
          </>
        ) : (
          <p className="text-sm text-slate-500">ログイン情報を取得できませんでした。</p>
        )}
      </Card>

      {/* 対人評価。信頼度スコア（AIによる自動判定）と対になる指標として並べる */}
      <Card>
        <SectionTitle>依頼者からの評価</SectionTitle>
        {reviews === undefined ? (
          <Skeleton className="h-16" />
        ) : reviews === null ? (
          <p className="text-xs text-slate-500">評価を取得できませんでした。</p>
        ) : reviews.reviewCount === 0 ? (
          <p className="text-xs text-slate-500">
            まだ評価はありません。撮影が合格すると、依頼者から5段階で評価されます。
          </p>
        ) : (
          <>
            <div className="flex items-center gap-3">
              <span className="text-3xl font-bold tabular-nums text-slate-800">
                {reviews.averageRating?.toFixed(1) ?? "—"}
              </span>
              <span className="min-w-0">
                <Stars value={reviews.averageRating ?? 0} size="lg" />
                <span className="mt-0.5 block text-xs text-slate-500">
                  {reviews.reviewCount}件の評価の平均（人による5段階評価）
                </span>
              </span>
            </div>

            <ul className="mt-3 space-y-2 border-t border-slate-100 pt-3">
              {reviews.reviews.slice(0, REVIEWS_ON_MY_PAGE).map((review) => (
                <li key={review.id} className="text-xs">
                  <div className="flex items-center gap-2">
                    <Stars value={review.rating} size="sm" />
                    <span className="min-w-0 truncate text-slate-500">{review.taskTitle}</span>
                  </div>
                  {review.tags.length > 0 && (
                    <div className="mt-1 flex flex-wrap gap-1">
                      {review.tags.map((tag) => (
                        <span
                          key={tag}
                          className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-bold text-slate-600"
                        >
                          {REVIEW_TAG_LABELS[tag]}
                        </span>
                      ))}
                    </div>
                  )}
                  {review.comment && (
                    <p className="mt-1 text-slate-600">{review.comment}</p>
                  )}
                </li>
              ))}
            </ul>
            {reviews.reviews.length > REVIEWS_ON_MY_PAGE && (
              <p className="mt-2 text-[11px] text-slate-400">
                最新{REVIEWS_ON_MY_PAGE}件を表示しています（全{reviews.reviewCount}件）
              </p>
            )}
          </>
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
