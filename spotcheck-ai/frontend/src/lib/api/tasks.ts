import { apiFetch } from "@/lib/api/client";
import type {
  AssignmentDetail,
  MyAssignmentItem,
  NearbyTask,
  TaskDetail,
  TaskListItem,
  TaskResults,
  TaskReviewResponse,
  TaskSummary,
} from "@/types/api";

export type CreateTaskInput = {
  title: string;
  description: string;
  locationLat: number;
  locationLng: number;
  locationAddress?: string | null;
  scheduledAt: string;
  deadlineAt: string;
  rewardAmount: number;
  requiredWorkerCount: number;
  referenceImages: File[];
};

/** `POST /api/tasks`（画面①→②）。AI審査が同期実行されるため時間がかかる。 */
export function createTask(input: CreateTaskInput): Promise<TaskReviewResponse> {
  const form = new FormData();
  form.set("title", input.title);
  form.set("description", input.description);
  form.set("locationLat", String(input.locationLat));
  form.set("locationLng", String(input.locationLng));
  if (input.locationAddress) form.set("locationAddress", input.locationAddress);
  form.set("scheduledAt", input.scheduledAt);
  form.set("deadlineAt", input.deadlineAt);
  form.set("rewardAmount", String(input.rewardAmount));
  form.set("requiredWorkerCount", String(input.requiredWorkerCount));
  input.referenceImages.forEach((file) => form.append("referenceImages", file));
  return apiFetch<TaskReviewResponse>("/api/tasks", { method: "POST", body: form });
}

export function duplicateTask(
  taskId: string,
  payload: { scheduledAt: string; deadlineAt: string },
): Promise<TaskReviewResponse> {
  return apiFetch<TaskReviewResponse>(`/api/tasks/${taskId}/duplicate`, {
    method: "POST",
    body: payload,
  });
}

export function resubmitTask(
  taskId: string,
  payload: { description: string; scheduledAt?: string; rewardAmount?: number },
): Promise<TaskReviewResponse> {
  return apiFetch<TaskReviewResponse>(`/api/tasks/${taskId}/resubmit`, {
    method: "POST",
    body: payload,
  });
}

export function listMyTasks(): Promise<{ tasks: TaskListItem[] }> {
  return apiFetch<{ tasks: TaskListItem[] }>("/api/tasks");
}

export function getTask(
  taskId: string,
  position?: { lat: number; lng: number },
): Promise<TaskDetail> {
  const query = position ? `?lat=${position.lat}&lng=${position.lng}` : "";
  return apiFetch<TaskDetail>(`/api/tasks/${taskId}${query}`);
}

export type NearbyQuery = {
  lat: number;
  lng: number;
  radiusKm?: number;
  sort?: "distance" | "reward" | "deadline";
};

export function listNearbyTasks(query: NearbyQuery): Promise<{ tasks: NearbyTask[] }> {
  const params = new URLSearchParams({
    lat: String(query.lat),
    lng: String(query.lng),
    radiusKm: String(query.radiusKm ?? 5),
    sort: query.sort ?? "distance",
  });
  return apiFetch<{ tasks: NearbyTask[] }>(`/api/tasks/nearby?${params.toString()}`);
}

export function acceptTask(taskId: string): Promise<{ assignment: AssignmentDetail }> {
  return apiFetch<{ assignment: AssignmentDetail }>(`/api/tasks/${taskId}/accept`, {
    method: "POST",
  });
}

export function cancelTask(taskId: string): Promise<{ task: TaskSummary }> {
  return apiFetch<{ task: TaskSummary }>(`/api/tasks/${taskId}/cancel`, { method: "POST" });
}

export function listMyAssignments(): Promise<{ assignments: MyAssignmentItem[] }> {
  return apiFetch<{ assignments: MyAssignmentItem[] }>("/api/assignments/mine");
}

export function getTaskResults(taskId: string): Promise<TaskResults> {
  return apiFetch<TaskResults>(`/api/tasks/${taskId}/results`);
}
