"use client";

/** 画面② AIリクエスト審査（docs/05-frontend.md 画面②）。 */

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { ScorePanel } from "@/components/task/ScorePanel";
import { Button, Card, EmptyState } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";
import { toMessage } from "@/lib/api/errorMessages";
import { getTaskReview, resubmitTask } from "@/lib/api/tasks";
import { formatCoords } from "@/lib/geo";
import { clearReview, loadReview, saveReview } from "@/lib/reviewHandoff";
import type { TaskReviewResponse } from "@/types/api";

const AUTO_REDIRECT_MS = 3000;

export default function ReviewPage() {
  const router = useRouter();
  const taskId = useSearchParams().get("taskId");
  const toast = useToast();
  const [data, setData] = useState<TaskReviewResponse | null | undefined>(undefined);
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const review = loadReview();
    if (review && (!taskId || review.task.id === taskId)) {
      setData(review);
      if (review.review.decision === "needs_info") {
        setDescription(review.task.description);
      }
      return;
    }
    if (!taskId) {
      setData(null);
      return;
    }
    getTaskReview(taskId)
      .then((result) => {
        saveReview(result);
        setData(result);
        if (result.review.decision === "needs_info") {
          setDescription(result.task.description);
        }
      })
      .catch((cause) => {
        toast.error(toMessage(cause));
        setData(null);
      });
  }, [taskId, toast]);

  // approved のときは3秒後に画面③へ自動遷移する
  useEffect(() => {
    if (data?.review.decision !== "approved") return;
    const timer = window.setTimeout(() => {
      clearReview();
      router.push(`/requests/${data.task.id}`);
    }, AUTO_REDIRECT_MS);
    return () => window.clearTimeout(timer);
  }, [data, router]);

  if (data === undefined) {
    return <p className="py-10 text-center text-sm text-slate-500">読み込み中…</p>;
  }

  if (data === null) {
    return (
      <EmptyState
        message="表示する審査結果がありません。依頼作成からやり直してください。"
        action={
          <Link href="/requests/new" className="text-sm font-bold text-client underline">
            依頼を作成する
          </Link>
        }
      />
    );
  }

  const { task, review } = data;

  const resubmit = async () => {
    setSubmitting(true);
    try {
      const next = await resubmitTask(task.id, { description: description.trim() });
      saveReview(next);
      setData(next);
      setDescription(next.review.decision === "needs_info" ? next.task.description : "");
      toast.success("再審査しました。");
    } catch (cause) {
      toast.error(toMessage(cause));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-5 md:mx-auto md:max-w-2xl">
      <header>
        <p className="text-xs font-bold text-ai">AIリクエスト審査（OrcaAI）</p>
        <h1 className="text-lg font-bold text-slate-800">{task.title}</h1>
      </header>

      <Card>
        <ScorePanel
          score={review.score}
          label="情報の十分性スコア"
          caption="情報の十分性スコア"
          items={[
            { label: "内容の妥当性チェック", ok: review.checks.validity === "pass" },
            { label: "リスクチェック", ok: review.checks.risk === "pass" },
            { label: "安全性チェック", ok: review.checks.safety === "pass" },
            { label: "重複・類似チェック", ok: review.checks.duplication === "pass" },
          ]}
        />
      </Card>

      {review.decision === "approved" && (
        <Card className="border-emerald-200 bg-emerald-50">
          <p className="text-sm font-bold text-emerald-800">
            スコア高 → 依頼を公開しました
          </p>
          <p className="mt-1 text-xs text-emerald-700">
            {task.reviewSummary}
          </p>
          <p className="mt-3 text-xs text-emerald-600">3秒後に進行状況へ移動します…</p>
          <div className="mt-3">
            <Button
              accent="worker"
              onClick={() => {
                clearReview();
                router.push(`/requests/${task.id}`);
              }}
            >
              今すぐ確認
            </Button>
          </div>
        </Card>
      )}

      {review.decision === "needs_info" && (
        <Card className="space-y-3 border-red-200 bg-red-50">
          <p className="text-sm font-bold text-red-800">スコア低 → 内容の補足をお願いします</p>
          <div className="rounded-lg bg-white/80 px-3 py-2 text-xs text-slate-600">
            <span className="font-bold">指定地点（保持されています）: </span>
            {task.locationAddress ?? formatCoords(task.locationLat, task.locationLng)}
          </div>
          <ul className="list-disc space-y-1 pl-5 text-xs text-red-700">
            {review.missingInfo.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
          <textarea
            rows={5}
            value={description}
            placeholder="元の詳細メッセージに不足情報を追記してください。"
            onChange={(e) => setDescription(e.target.value)}
            className="w-full rounded-xl border border-red-200 bg-white px-3 py-2.5 text-sm"
          />
          <Button
            accent="client"
            onClick={() => void resubmit()}
            loading={submitting}
            disabled={description.trim().length < 10}
          >
            再審査する
          </Button>
        </Card>
      )}

      {review.decision === "rejected" && (
        <Card className="space-y-3 border-red-200 bg-red-50">
          <p className="text-sm font-bold text-red-800">この依頼は公開できません</p>
          <p className="text-xs leading-relaxed text-red-700">
            {review.rejectionReason ?? "安全性の基準に適合しないため却下されました。"}
          </p>
          {/* 却下された依頼の言い換えによる回避を促さないため、編集フォームは出さない */}
          <Button
            accent="neutral"
            onClick={() => {
              clearReview();
              router.push("/requests/new");
            }}
          >
            新しい依頼を作成
          </Button>
        </Card>
      )}
    </div>
  );
}
