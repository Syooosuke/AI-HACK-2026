/**
 * `error.code` に応じた日本語メッセージ（docs/05-frontend.md 5節）。
 * バックエンドのメッセージも日本語だが、UI文言として出したいものはここで上書きする。
 */

import { ApiError } from "@/lib/api/client";

const MESSAGES: Record<string, string> = {
  NETWORK_ERROR: "サーバーに接続できません。通信環境を確認してください。",
  UNAUTHENTICATED: "デモユーザーが選択されていません。トップから選び直してください。",
  FORBIDDEN: "この操作を行う権限がありません。ユーザーを切り替えてください。",
  TASK_NOT_FOUND: "依頼が見つかりません。一覧から選び直してください。",
  SUBMISSION_NOT_FOUND: "提出が見つかりません。",
  ASSIGNMENT_NOT_FOUND: "受注情報が見つかりません。",
  TASK_FULL: "他のワーカーが受注済みです。",
  ALREADY_ACCEPTED: "すでにこの依頼を受注しています。",
  INVALID_STATE: "現在の状態ではこの操作を行えません。",
  RETAKE_LIMIT_EXCEEDED: "再撮影の上限に達しています。",
  VALIDATION_ERROR: "入力内容を確認してください。",
  FILE_TOO_LARGE: "画像サイズが大きすぎます（15MBまで）。",
  AI_SERVICE_ERROR: "AIの処理に失敗しました。もう一度お試しください。",
  STORAGE_ERROR: "画像の保存に失敗しました。もう一度お試しください。",
  INTERNAL_ERROR: "サーバーでエラーが発生しました。",
};

export function toMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return MESSAGES[error.code] ?? error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "予期しないエラーが発生しました。";
}
