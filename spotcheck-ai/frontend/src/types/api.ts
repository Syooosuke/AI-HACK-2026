/**
 * バックエンドのスキーマに対応する型（docs/03-api.md）。
 * JSONキーは camelCase。
 */

export type UserRole = "client" | "worker";

export type TaskStatus =
  | "screening"
  | "rejected"
  | "needs_info"
  | "open"
  | "in_progress"
  | "completed"
  | "expired"
  | "cancelled";

export type AssignmentStatus =
  | "accepted"
  | "submitted"
  | "approved"
  | "failed"
  | "cancelled"
  | "expired";

export type ValidationStatus = "pending" | "processing" | "approved" | "rejected" | "error";

export type IssueCode =
  | "SUBJECT_MISSING"
  | "TOO_DARK"
  | "TOO_BLURRY"
  | "ANGLE_MISMATCH"
  | "TOO_FAR"
  | "OBSTRUCTED"
  | "LOCATION_MISMATCH"
  | "TIMESTAMP_MISMATCH"
  | "OTHER";

export type HealthResponse = {
  status: "ok" | "degraded";
  appEnv: string;
  time: string;
  dependencies: {
    database: { configured: boolean; url: string };
    storage: { backend: "supabase" | "local"; bucketRaw: string; bucketProcessed: string };
    orca: { stubMode: boolean; routerLight: string; routerVision: string };
  };
  configWarnings: string[];
};

export type DemoUser = {
  id: string;
  role: UserRole;
  displayName: string;
  trustScore: number;
  completedTaskCount: number;
  avatarUrl: string | null;
};

export type ReviewChecks = {
  safety: "pass" | "fail";
  validity: "pass" | "fail";
  risk: "pass" | "fail";
  duplication: "pass" | "fail";
};

export type ReviewResult = {
  decision: "approved" | "needs_info" | "rejected";
  score: number;
  checks: ReviewChecks;
  missingInfo: string[];
  rejectionReason: string | null;
};

export type TaskSummary = {
  id: string;
  status: TaskStatus;
  title: string;
  description: string;
  locationLat: number;
  locationLng: number;
  locationAddress: string | null;
  reviewScore: number | null;
  reviewSummary: string | null;
  scheduledAt: string;
  deadlineAt: string;
  rewardAmount: number;
  requiredWorkerCount: number;
};

export type TaskReviewResponse = {
  task: TaskSummary;
  review: ReviewResult;
};

export type TaskListItem = {
  id: string;
  title: string;
  status: TaskStatus;
  rewardAmount: number;
  requiredWorkerCount: number;
  approvedWorkerCount: number;
  acceptedWorkerCount: number;
  scheduledAt: string;
  deadlineAt: string;
  locationAddress: string | null;
  createdAt: string;
};

export type TimelineStep = {
  step: string;
  label: string;
  status: "done" | "current" | "pending";
  at: string | null;
};

export type MyAssignment = {
  id: string;
  status: AssignmentStatus;
  retakeCount: number;
  remainingRetakes: number;
  latestSubmissionId: string | null;
};

export type ReferenceImage = {
  id: string;
  imageUrl: string;
  sortOrder: number;
};

/** 画面⑤の依頼者行に出す要約（docs/03-api.md 3.4）。 */
export type RequesterSummary = {
  id: string;
  displayName: string;
  avatarUrl: string | null;
  publishedTaskCount: number;
  /** 母数0のときは null */
  completionRate: number | null;
};

export type RequesterStats = {
  publishedTaskCount: number;
  completedTaskCount: number;
  completionRate: number | null;
};

export type WorkerStats = {
  /** 5段階へ換算済み */
  trustScore: number;
  approvedSubmissionCount: number;
};

/** 閲覧専用の公開プロフィール。email / loginId は含まれない。 */
export type PublicProfile = {
  id: string;
  displayName: string;
  avatarUrl: string | null;
  joinedAt: string;
  asRequester: RequesterStats;
  asWorker: WorkerStats;
};

export type TaskDetail = {
  id: string;
  title: string;
  description: string;
  locationLat: number;
  locationLng: number;
  locationAddress: string | null;
  scheduledAt: string;
  deadlineAt: string;
  rewardAmount: number;
  requiredWorkerCount: number;
  approvedWorkerCount: number;
  remainingSlots: number;
  status: TaskStatus;
  reviewSummary: string | null;
  referenceImages: ReferenceImage[];
  requester: RequesterSummary | null;
  timeline: TimelineStep[] | null;
  distanceKm: number | null;
  myAssignment: MyAssignment | null;
};

export type NearbyTask = {
  id: string;
  title: string;
  rewardAmount: number;
  distanceKm: number;
  scheduledAt: string;
  deadlineAt: string;
  locationLat: number;
  locationLng: number;
  remainingSlots: number;
  requiredWorkerCount: number;
};

export type AssignmentDetail = {
  id: string;
  taskId: string;
  status: AssignmentStatus;
  retakeCount: number;
  remainingRetakes: number;
};

export type MyAssignmentItem = AssignmentDetail & {
  title: string;
  rewardAmount: number;
  deadlineAt: string;
  locationLat: number;
  locationLng: number;
  latestSubmissionId: string | null;
};

export type Issue = {
  code: IssueCode;
  message: string;
};

export type SubmissionCreateResponse = {
  submission: { id: string; attemptNo: number; aiValidationStatus: ValidationStatus };
  pollUrl: string;
};

export type SubmissionStatus = {
  id: string;
  attemptNo: number;
  aiValidationStatus: ValidationStatus;
  aiScore: number | null;
  realityScore: number | null;
  processedImageUrl: string | null;
  checks: {
    framingOk: boolean;
    subjectPresent: boolean;
    locationVerified: boolean;
    privacyMasked: boolean;
  };
  issues: Issue[];
  retake: { allowed: boolean; remaining: number };
  assignmentStatus: AssignmentStatus;
};

export type LocationCheck = {
  distance_m?: number;
  within_tolerance?: boolean;
  timestamp_delta_seconds?: number;
  timestamp_consistent?: boolean;
  exif_gps_present?: boolean | null;
  exif_gps_conflict?: boolean | null;
  flags?: string[];
  pending_checks?: string[];
};

export type TaskResultItem = {
  submissionId: string;
  processedImageUrl: string | null;
  capturedAt: string;
  capturedLat: number;
  capturedLng: number;
  locationLabel: string | null;
  realityScore: number | null;
  aiSummary: string | null;
  locationCheck: LocationCheck | null;
  worker: { displayName: string; trustScore: number; avatarUrl: string | null };
};

export type TaskResults = {
  taskId: string;
  status: TaskStatus;
  resultSummary: string | null;
  approvedCount: number;
  requiredWorkerCount: number;
  results: TaskResultItem[];
};
