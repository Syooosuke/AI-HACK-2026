import { apiFetch } from "@/lib/api/client";
import type {
  SubmissionCreateResponse,
  SubmissionStatus,
  WorkerReview,
  WorkerReviewTag,
} from "@/types/api";

export type SubmitInput = {
  assignmentId: string;
  image: Blob;
  capturedLat: number;
  capturedLng: number;
  capturedAccuracyM?: number | null;
  /** 端末側の撮影時刻（ISO8601）。シャッターを押した瞬間の時刻。 */
  capturedAt: string;
  deviceInfo?: Record<string, unknown>;
};

/** `POST /api/submissions`（画面⑥ / D-02）。画像・位置・時刻を同一リクエストで送る。 */
export function createSubmission(input: SubmitInput): Promise<SubmissionCreateResponse> {
  const form = new FormData();
  form.set("assignmentId", input.assignmentId);
  form.set("image", input.image, "capture.jpg");
  form.set("capturedLat", String(input.capturedLat));
  form.set("capturedLng", String(input.capturedLng));
  if (input.capturedAccuracyM != null) {
    form.set("capturedAccuracyM", String(input.capturedAccuracyM));
  }
  form.set("capturedAt", input.capturedAt);
  if (input.deviceInfo) {
    form.set("deviceInfo", JSON.stringify(input.deviceInfo));
  }
  return apiFetch<SubmissionCreateResponse>("/api/submissions", { method: "POST", body: form });
}

export function getSubmission(submissionId: string): Promise<SubmissionStatus> {
  return apiFetch<SubmissionStatus>(`/api/submissions/${submissionId}`);
}

export function createWorkerReview(
  submissionId: string,
  input: { rating: number; tags: WorkerReviewTag[]; comment?: string },
): Promise<WorkerReview> {
  return apiFetch<WorkerReview>(`/api/submissions/${submissionId}/review`, {
    method: "POST",
    body: input,
  });
}
