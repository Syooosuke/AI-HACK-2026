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

/** バックエンドの ALLOWED_IMAGE_TYPES と揃える。 */
const ACCEPTED_TYPES = "image/jpeg,image/png,image/webp";

export default function MyPage() {
  const router = useRouter();
  const toast = useToast();
  const fileInput = useRef<HTMLInputElement>(null);
  const [user, setUser] = useState<AuthUser | null | undefined>(undefined);
  const [saving, setSaving] = useState(false);
  const [isReviewModalOpen, setIsReviewModalOpen] = useState(false);
  // undefined=読み込み中 / null=取得失敗
  const [reviews, setReviews] = useState<ReceivedWorkerReviews | null | undefined>(undefined);

  useEffect(() => {
    const sync = () => setUser(getCurrentUser());
    sync();
    return subscribeSession(sync);
  }, []);

  useEffect(() => {
    if (!isReviewModalOpen) return;

    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setIsReviewModalOpen(false);
    };
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", closeOnEscape);

    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [isReviewModalOpen]);

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
                <div className="mt-2">
                  <InfoRow label="完了した依頼" value={`${user.completedTaskCount}件`} />
                </div>
              </div>
            </div>

            {/* AIの信頼度スコアと、人による評価を同じプロフィール枠で確認できるようにする */}
            <div className="mt-4 border-t border-slate-100 pt-4">
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
                        総評価件数{reviews.reviewCount}
                      </span>
                    </span>
                    <button
                      type="button"
                      onClick={() => setIsReviewModalOpen(true)}
                      className="ml-auto shrink-0 rounded-lg border border-slate-300 px-3 py-2 text-xs font-bold text-slate-600 transition hover:bg-slate-50"
                    >
                      詳細を見る
                    </button>
                  </div>
                </>
              )}
            </div>
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

      {isReviewModalOpen && reviews && reviews.reviewCount > 0 && (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/40 p-0 sm:items-center sm:p-4"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setIsReviewModalOpen(false);
          }}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="review-modal-title"
            className="max-h-[85vh] w-full overflow-hidden rounded-t-2xl bg-white shadow-xl sm:max-w-lg sm:rounded-2xl"
          >
            <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
              <div>
                <h2 id="review-modal-title" className="text-base font-bold text-slate-800">
                  依頼者からの評価
                </h2>
                <p className="mt-0.5 text-xs text-slate-500">
                  平均 {reviews.averageRating?.toFixed(1) ?? "—"}・全{reviews.reviewCount}件
                </p>
              </div>
              <button
                type="button"
                onClick={() => setIsReviewModalOpen(false)}
                aria-label="評価の詳細を閉じる"
                className="flex h-9 w-9 items-center justify-center rounded-full text-xl text-slate-400 hover:bg-slate-100 hover:text-slate-600"
              >
                ×
              </button>
            </div>

            <ul className="max-h-[calc(85vh-70px)] space-y-3 overflow-y-auto p-4">
              {reviews.reviews.map((review) => (
                <li key={review.id} className="rounded-xl border border-slate-100 bg-slate-50 p-3 text-xs">
                  <div className="flex items-center gap-2">
                    <Stars value={review.rating} size="sm" />
                    <span className="min-w-0 truncate font-bold text-slate-600">
                      {review.taskTitle}
                    </span>
                  </div>
                  {review.tags.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {review.tags.map((tag) => (
                        <span
                          key={tag}
                          className="rounded-full bg-white px-2 py-0.5 text-[10px] font-bold text-slate-600"
                        >
                          {REVIEW_TAG_LABELS[tag]}
                        </span>
                      ))}
                    </div>
                  )}
                  {review.comment && (
                    <p className="mt-2 leading-relaxed text-slate-600">{review.comment}</p>
                  )}
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}
