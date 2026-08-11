"use client";

/** 画面⑥ 撮影・アップロード（D-02）。CameraView からの結果を提出APIへ送る。 */

import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { CameraView, type CaptureResult } from "@/components/capture/CameraView";
import { Button, Card, Spinner } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";
import { toMessage } from "@/lib/api/errorMessages";
import { createSubmission } from "@/lib/api/submissions";
import { getTask } from "@/lib/api/tasks";
import type { MyAssignment } from "@/types/api";

export default function CapturePage() {
  const { taskId } = useParams<{ taskId: string }>();
  const router = useRouter();
  const toast = useToast();
  const [assignment, setAssignment] = useState<MyAssignment | null | undefined>(undefined);
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    try {
      const task = await getTask(taskId);
      setAssignment(task.myAssignment);
    } catch (cause) {
      setAssignment(null);
      toast.error(toMessage(cause));
    }
  }, [taskId, toast]);

  useEffect(() => {
    void load();
  }, [load]);

  const submit = async (result: CaptureResult) => {
    if (!assignment || submitting) return;
    setSubmitting(true);
    try {
      const response = await createSubmission({
        assignmentId: assignment.id,
        image: result.blob,
        capturedLat: result.metadata.lat,
        capturedLng: result.metadata.lng,
        capturedAccuracyM: result.metadata.accuracyM,
        capturedAt: result.metadata.capturedAt,
        deviceInfo: {
          userAgent: navigator.userAgent,
          platform: navigator.platform,
          screen: `${window.screen.width}x${window.screen.height}`,
          captureMode: result.captureMode,
        },
      });
      router.replace(
        `/jobs/${taskId}/status?submissionId=${response.submission.id}`,
      );
    } catch (cause) {
      toast.error(toMessage(cause));
      setSubmitting(false);
    }
  };

  if (assignment === undefined) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-black">
        <Spinner className="h-8 w-8 border-white/30 border-t-white" />
      </div>
    );
  }

  if (!assignment || assignment.status !== "accepted") {
    return (
      <div className="mx-auto max-w-app px-4 py-10">
        <Card className="space-y-3">
          <p className="text-sm font-bold text-slate-800">この依頼は撮影できません</p>
          <p className="text-xs text-slate-600">
            {assignment
              ? "現在の受注状態では提出できません。検品結果を確認してください。"
              : "先に依頼を受注してください。"}
          </p>
          <Button accent="neutral" onClick={() => router.replace(`/jobs/${taskId}`)}>
            依頼詳細へ戻る
          </Button>
        </Card>
      </div>
    );
  }

  return (
    <CameraView
      submitting={submitting}
      attemptLabel={`${assignment.retakeCount + 1}回目 / 残り再撮影${assignment.remainingRetakes}回`}
      onClose={() => router.replace(`/jobs/${taskId}`)}
      onSubmit={(result) => void submit(result)}
    />
  );
}
