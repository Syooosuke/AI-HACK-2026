/**
 * バックエンドのスキーマに対応する型（docs/03-api.md）。
 * JSONキーは camelCase。
 */

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

export type NotificationType =
  | "task_approved"
  | "task_needs_info"
  | "task_rejected"
  | "task_accepted"
  | "submission_approved"
  | "submission_retake"
  | "submission_failed"
  | "task_completed"
  | "task_expired";

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

/** ログイン中のユーザー（`GET /api/auth/me` / ログイン応答）。 */
export type AuthUser = {
  id: string;
  loginId: string;
  displayName: string;
  trustScore: number;
  completedTaskCount: number;
  avatarUrl: string | null;
};

export type AuthResponse = {
  token: string;
  tokenType: string;
  /** トークンの有効期間（秒）。 */
  expiresIn: number;
  user: AuthUser;
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
  minWorkerRating: number | null;
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

export type RequesterStats = {
  publishedTaskCount: number;
  completedTaskCount: number;
  completionRate: number | null;
};

export type WorkerStats = {
  /** 0〜100。画面ではゲージで表示する。 */
  trustScore: number;
  approvedSubmissionCount: number;
  averageRating: number | null;
  reviewCount: number;
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

/** 投稿カードの左上に出すタグ。 */
export type TaskBadge = "sold" | "new" | "hot";

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
  /** 受注できるワーカーの最低平均評価。null なら条件なし */
  minWorkerRating: number | null;
  status: TaskStatus;
  reviewSummary: string | null;
  referenceImages: ReferenceImage[];
  createdAt: string;
  owner: TaskOwner | null;
  thumbnailUrl: string | null;
  badges: TaskBadge[];
  likeCount: number;
  isLiked: boolean;
  viewCount: number;
  isMine: boolean;
  timeline: TimelineStep[] | null;
  distanceKm: number | null;
  myAssignment: MyAssignment | null;
};

/** 依頼主（投稿者）。 */
export type TaskOwner = {
  /** 公開プロフィール `/users/[id]` への導線に使う */
  id: string;
  displayName: string;
  /** 0〜100。画面ではゲージで表示する。 */
  trustScore: number;
  completedTaskCount: number;
  avatarUrl: string | null;
  publishedTaskCount: number;
  /** 母数0のときは null */
  completionRate: number | null;
};

/** 投稿一覧（ホーム・さがす・ハート欄）に並べる1件分。 */
export type NearbyTask = {
  id: string;
  title: string;
  rewardAmount: number;
  /** 中心座標が分かる場合のみ入る（ハート欄では null）。 */
  distanceKm: number | null;
  scheduledAt: string;
  deadlineAt: string;
  locationLat: number;
  locationLng: number;
  locationAddress: string | null;
  remainingSlots: number;
  requiredWorkerCount: number;
  minWorkerRating: number | null;
  status: TaskStatus;
  createdAt: string;
  thumbnailUrl: string | null;
  thumbnailSource: string | null;
  badges: TaskBadge[];
  likeCount: number;
  isLiked: boolean;
  viewCount: number;
  isMine: boolean;
};

export type LikeResult = {
  taskId: string;
  liked: boolean;
  likeCount: number;
};

/** 保存した検索条件（ハート欄の下半分）。 */
export type SavedSearch = {
  id: string;
  label: string;
  centerLat: number;
  centerLng: number;
  locationAddress: string | null;
  radiusKm: number;
  sort: "distance" | "reward" | "deadline";
  lastMatchCount: number | null;
  createdAt: string;
};

/** お知らせ（画面下部タブ）の1件。 */
export type NotificationItem = {
  id: string;
  type: NotificationType;
  title: string;
  body: string | null;
  taskId: string | null;
  submissionId: string | null;
  readAt: string | null;
  createdAt: string;
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
  workerReview: WorkerReview | null;
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
  /** `trustScore` は 0〜100。画面ではゲージで表示する。 */
  worker: { id: string; displayName: string; trustScore: number; avatarUrl: string | null };
  workerReview: WorkerReview | null;
};

export type WorkerReviewTag =
  | "as_requested"
  | "clear_photo"
  | "fast_response"
  | "accurate_location";

export type WorkerReview = {
  id: string;
  submissionId: string;
  workerId: string;
  rating: number;
  tags: WorkerReviewTag[];
  comment: string | null;
  createdAt: string;
};

export type ReceivedWorkerReview = {
  id: string;
  submissionId: string;
  taskId: string;
  taskTitle: string;
  rating: number;
  tags: WorkerReviewTag[];
  comment: string | null;
  createdAt: string;
};

export type ReceivedWorkerReviews = {
  reviews: ReceivedWorkerReview[];
  averageRating: number | null;
  reviewCount: number;
};

export type TaskResults = {
  taskId: string;
  status: TaskStatus;
  resultSummary: string | null;
  approvedCount: number;
  requiredWorkerCount: number;
  results: TaskResultItem[];
};
