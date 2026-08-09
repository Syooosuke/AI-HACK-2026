"use client";

/** トースト表示（docs/05-frontend.md 5節）。API失敗時の日本語メッセージを出す。 */

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

type ToastTone = "error" | "success" | "info";
type Toast = { id: number; message: string; tone: ToastTone };

type ToastApi = {
  show: (message: string, tone?: ToastTone) => void;
  error: (message: string) => void;
  success: (message: string) => void;
};

const ToastContext = createContext<ToastApi | null>(null);

const TONE_CLASS: Record<ToastTone, string> = {
  error: "bg-red-600",
  success: "bg-emerald-600",
  info: "bg-slate-800",
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const show = useCallback((message: string, tone: ToastTone = "info") => {
    const id = Date.now() + Math.random();
    setToasts((current) => [...current, { id, message, tone }]);
    window.setTimeout(() => {
      setToasts((current) => current.filter((toast) => toast.id !== id));
    }, 4000);
  }, []);

  const api = useMemo<ToastApi>(
    () => ({
      show,
      error: (message: string) => show(message, "error"),
      success: (message: string) => show(message, "success"),
    }),
    [show],
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 bottom-24 z-50 flex flex-col items-center gap-2 px-4">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            role="alert"
            className={`w-full max-w-app rounded-xl px-4 py-3 text-sm font-medium text-white shadow-lg ${TONE_CLASS[toast.tone]}`}
          >
            {toast.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error("useToast は ToastProvider の内側で使ってください。");
  }
  return context;
}
