/** 認証API（`/api/auth/*`）。ログインと新規登録はトークン未取得のため auth: false で呼ぶ。 */

import { apiFetch } from "@/lib/api/client";
import type { AuthResponse, AuthUser } from "@/types/api";

export type LoginInput = {
  loginId: string;
  password: string;
};

export type SignupInput = LoginInput & {
  displayName: string;
};

export function login(input: LoginInput): Promise<AuthResponse> {
  return apiFetch<AuthResponse>("/api/auth/login", {
    method: "POST",
    body: input,
    auth: false,
  });
}

export function signup(input: SignupInput): Promise<AuthResponse> {
  return apiFetch<AuthResponse>("/api/auth/signup", {
    method: "POST",
    body: input,
    auth: false,
  });
}

/** 保持しているトークンの有効性確認と、最新のユーザー情報の取得を兼ねる。 */
export function fetchMe(): Promise<{ user: AuthUser }> {
  return apiFetch<{ user: AuthUser }>("/api/auth/me");
}
