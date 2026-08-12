"use client";

/**
 * 画面⑦ AI画像検品・安全処理 ＋ 画面⑧ 再撮影フィードバック
 * （docs/05-frontend.md 画面⑦・⑧）。
 *
 * **検品は実測30秒〜15分かかる**ため、段階的バックオフでポーリングする
 * （最初の30秒は2秒間隔 → 以降 5秒 → 15秒 → 30秒）。
 * タブを離れている間はブラウザが setTimeout を抑制するので、復帰時に即座に1回取得する。
 */

import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { IssueList } from "@/components/task/IssueList";
import { PollingIndicator } from "@/components/task/PollingIndicator";
import { ScorePanel } from "@/components/task/ScorePanel";
import { Button, Card, EmptyState, SectionTitle, Skeleton } from "@/components/ui";
import { ValidationBadge } from "@/components/ui/StatusBadge";
import { useToast } from "@/components/ui/Toast";
import { toMessage } from "@/lib/api/errorMessages";
import { getSubmission } from "@/lib/api/submissions";
import { getTask } from "@/lib/api/tasks";
import { formatElapsed, nextPollInterval, shouldStopPolling } from "@/lib/polling";
import type { SubmissionStatus } from "@/types/api";

export default function SubmissionStatusPage() {
  const { taskId } = useParams<{ taskId: string }>();
  const submissionId = useSearchParams().get("submissionId");
  const router = useRouter();
  const toast = useToast();
  const [data, setData] = useState<SubmissionStatus | null>(null);
  const [reward, setReward] = useState<number | null>(null);
  const [stopped, setStopped] = useState(false);
  const [elapsedMs, setElapsedMs] = useState(0);
  const startedAtRef = useRef(Date.now());

  // 報酬確定の表示に依頼の報酬額を使う（docs/05-frontend.md 画面⑦）
  useEffect(() => {
    getTask(taskId)
      .then((task) => setReward(task.rewardAmount))
      .catch(() => setReward(null));
  }, [taskId]);

  /** 最新の検品状況を取得する。戻り値は「検品が終わったか」。 */
  const load = useCallback(async () => {
    if (!submissionId) return true;
    try {
      const next = await getSubmission(submissionId);
      setData(next);
      // error も終了状態として扱う（再送信の案内を出すため、待ち続けない）
      return next.aiValidationStatus !== "pending" && next.aiValidationStatus !== "processing";
    } catch (cause) {
      toast.error(toMessage(cause));
      return true;
    }
  }, [submissionId, toast]);

  useEffect(() => {
    if (!submissionId) return;
    let timer: number | undefined;
    let active = true;
    let finished = false;
    startedAtRef.current = Date.now();

    const tick = async () => {
      const done = await load();
      if (!active) return;

      const elapsed = Date.now() - startedAtRef.current;
      setElapsedMs(elapsed);

      if (done) {
        finished = true;
        return;
      }
      if (shouldStopPolling(elapsed)) {
        finished = true;
        setStopped(true);
        return;
      }
      timer = window.setTimeout(() => void tick(), nextPollInterval(elapsed));
    };
    void tick();

    // タブを離れている間は setTimeout が抑制されるため、復帰時に即座に取り直す
    const onVisible = () => {
      if (document.visibilityState !== "visible" || finished || !active) return;
      if (timer) window.clearTimeout(timer);
      void tick();
    };
    document.addEventListener("visibilitychange", onVisible);

    return () => {
      active = false;
      if (timer) window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [load, submissionId]);

  if (!submissionId) {
    return <EmptyState message="表示する提出が指定されていません。" />;
  }

  if (!data) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-8 w-40" />
        <Skeleton className="h-64" />
      </div>
    );
  }

  const processing =
    data.aiValidationStatus === "pending" || data.aiValidationStatus === "processing";
  const approved = data.aiValidationStatus === "approved";
  const rejected = data.aiValidationStatus === "rejected";
  const errored = data.aiValidationStatus === "error";

  return (
    <div className="space-y-5 md:mx-auto md:max-w-2xl">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs font-bold text-ai">AI画像検品・安全処理</p>
          <h1 className="text-lg font-bold text-slate-800">{data.attemptNo}回目の提出</h1>
        </div>
        <ValidationBadge status={data.aiValidationStatus} />
      </div>

      <Card>
        <ScorePanel
          score={processing ? null : data.aiScore}
          label="画像検品スコア"
          caption={processing ? "検品しています…" : "画像検品スコア"}
          items={[
            { label: "構図確認", ok: processing ? null : data.checks.framingOk },
            { label: "対象物確認", ok: processing ? null : data.checks.subjectPresent },
            { label: "位置・時刻確認", ok: processing ? null : data.checks.locationVerified },
            { label: "顔 / ナンバー保護", ok: processing ? null : data.checks.privacyMasked },
          ]}
        />
      </Card>

      {processing && !stopped && (
        <PollingIndicator
          label={`検品状況を確認しています（経過 ${formatElapsed(elapsedMs)}）`}
          hint="AIの検品は30秒〜15分ほどかかります。このまま開いたままでも、閉じてあとから確認しても構いません。"
        />
      )}
      {processing && stopped && (
        <Card className="space-y-3 border-slate-300 bg-slate-100">
          <p className="text-sm font-bold text-slate-700">自動更新を停止しました</p>
          <p className="text-xs leading-relaxed text-slate-600">
            検品に15分以上かかっています。結果は「受注した依頼」からいつでも確認できます。
          </p>
          <div className="flex gap-2">
            <Button
              accent="worker"
              onClick={() => {
                setStopped(false);
                startedAtRef.current = Date.now();
                setElapsedMs(0);
                void load();
              }}
            >
              もう一度確認する
            </Button>
            <Button accent="neutral" onClick={() => router.push("/jobs")}>
              受注した依頼へ
            </Button>
          </div>
        </Card>
      )}

      {approved && (
        <Card className="space-y-3 border-emerald-200 bg-emerald-50">
          <p className="text-sm font-bold text-emerald-800">
            スコア高 → マスク / ブラー処理を実施しました
          </p>
          <p className="text-xs text-emerald-700">
            報酬が確定しました。お疲れさまでした。
            {reward != null && (
              <span className="ml-1 font-bold">（¥{reward.toLocaleString()}）</span>
            )}
          </p>
          {data.processedImageUrl && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={data.processedImageUrl}
              alt="安全処理済みの画像"
              className="w-full rounded-xl"
            />
          )}
          <Button accent="worker" onClick={() => router.push("/home")}>
            依頼一覧へ戻る
          </Button>
        </Card>
      )}

      {rejected && (
        <Card className="space-y-3 border-red-200 bg-red-50">
          <p className="text-sm font-bold text-red-800">スコア低 → 再撮影をお願いします</p>
          <SectionTitle>指摘内容</SectionTitle>
          <IssueList issues={data.issues} />
          {data.retake.allowed ? (
            <>
              <p className="text-xs font-bold text-red-700">
                あと{data.retake.remaining}回まで再撮影できます
              </p>
              <Button
                accent="worker"
                onClick={() => router.push(`/jobs/${taskId}/capture`)}
              >
                再撮影する
              </Button>
            </>
          ) : (
            <>
              <p className="text-xs leading-relaxed text-red-700">
                再撮影の上限に達したため、この依頼は他のワーカーへ再開放されました。
              </p>
              <Button accent="neutral" onClick={() => router.push("/home")}>
                依頼一覧へ戻る
              </Button>
            </>
          )}
        </Card>
      )}

      {errored && (
        <Card className="space-y-3 border-slate-300 bg-slate-100">
          <p className="text-sm font-bold text-slate-700">
            システム側の問題で検品できませんでした
          </p>
          <p className="text-xs text-slate-600">
            もう一度送信してください（再撮影回数は消費されません）。
          </p>
          <Button accent="worker" onClick={() => router.push(`/jobs/${taskId}/capture`)}>
            もう一度撮影する
          </Button>
        </Card>
      )}
    </div>
  );
}
