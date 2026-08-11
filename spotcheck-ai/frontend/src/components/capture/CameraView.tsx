"use client";

/**
 * 画面⑥ のカメラ（D-02 / docs/05-frontend.md 画面⑥）。
 *
 * 1. getUserMedia({ video: { facingMode: "environment" } })
 * 2. watchPosition() で位置を追跡し続ける
 * 3. シャッター押下の瞬間に canvas へ描画して JPEG(quality 0.9) を生成し、
 *    そのときの座標・精度・時刻をまとめて返す
 *
 * **位置情報が取れていないあいだシャッターは押せない。** 位置情報なしの提出は許可しない。
 * getUserMedia が使えない環境ではファイル選択にフォールバックする。
 */

import { useCallback, useEffect, useRef, useState } from "react";

import {
  GpsBadge,
  MetadataBar,
  TimestampOverlay,
  type CaptureMetadata,
} from "@/components/capture/MetadataOverlay";
import { Button } from "@/components/ui";

const JPEG_QUALITY = 0.9;

export type CaptureResult = {
  blob: Blob;
  previewUrl: string;
  metadata: CaptureMetadata;
  captureMode: "camera" | "fallback_upload";
};

/** トーチ（ライト）は標準の型定義に含まれないため、必要な部分だけ独自に宣言する。 */
type TorchTrack = {
  getCapabilities?: () => { torch?: boolean };
  applyConstraints: (constraints: { advanced: Array<{ torch: boolean }> }) => Promise<void>;
};

function asTorchTrack(track: MediaStreamTrack | undefined): TorchTrack | undefined {
  return track as unknown as TorchTrack | undefined;
}

export function CameraView({
  onSubmit,
  onClose,
  submitting,
  attemptLabel,
}: {
  onSubmit: (result: CaptureResult) => void;
  onClose: () => void;
  submitting: boolean;
  attemptLabel: string;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const watchIdRef = useRef<number | null>(null);

  const [facingMode, setFacingMode] = useState<"environment" | "user">("environment");
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [position, setPosition] = useState<GeolocationCoordinates | null>(null);
  const [geoError, setGeoError] = useState<string | null>(null);
  const [now, setNow] = useState(() => new Date());
  const [captured, setCaptured] = useState<CaptureResult | null>(null);
  const [torchAvailable, setTorchAvailable] = useState(false);
  const [torchOn, setTorchOn] = useState(false);

  // ---- 時刻表示 ----
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  // ---- 位置情報の追跡 ----
  useEffect(() => {
    if (!navigator.geolocation) {
      setGeoError("この端末では位置情報を取得できません。");
      return;
    }
    watchIdRef.current = navigator.geolocation.watchPosition(
      (pos) => {
        setPosition(pos.coords);
        setGeoError(null);
      },
      (error) => setGeoError(geolocationMessage(error)),
      { enableHighAccuracy: true, maximumAge: 0, timeout: 15000 },
    );
    return () => {
      if (watchIdRef.current != null) navigator.geolocation.clearWatch(watchIdRef.current);
    };
  }, []);

  // ---- カメラの起動 ----
  const stopStream = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }, []);

  useEffect(() => {
    if (captured) return; // プレビュー中はカメラを止めない（撮り直しで再利用する）
    let cancelled = false;

    const start = async () => {
      if (!navigator.mediaDevices?.getUserMedia) {
        setCameraError(
          "この環境ではカメラを利用できません（HTTPS が必要です）。ファイルを選択して提出してください。",
        );
        return;
      }
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode },
          audio: false,
        });
        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }
        stopStream();
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play().catch(() => undefined);
        }
        const track = asTorchTrack(stream.getVideoTracks()[0]);
        setTorchAvailable(Boolean(track?.getCapabilities?.().torch));
        setCameraError(null);
      } catch {
        setCameraError(
          "カメラを起動できませんでした。権限を許可するか、ファイルを選択して提出してください。",
        );
      }
    };
    void start();

    return () => {
      cancelled = true;
    };
  }, [facingMode, captured, stopStream]);

  useEffect(() => stopStream, [stopStream]);

  const toggleTorch = async () => {
    const track = asTorchTrack(streamRef.current?.getVideoTracks()[0]);
    if (!track) return;
    const next = !torchOn;
    try {
      await track.applyConstraints({ advanced: [{ torch: next }] });
      setTorchOn(next);
    } catch {
      setTorchAvailable(false);
    }
  };

  const gpsReady = position != null;

  const shoot = () => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || !position) return;

    canvas.width = video.videoWidth || 1280;
    canvas.height = video.videoHeight || 960;
    const context = canvas.getContext("2d");
    if (!context) return;
    context.drawImage(video, 0, 0, canvas.width, canvas.height);

    // シャッターを押した瞬間の座標・時刻を確定させる
    const metadata: CaptureMetadata = {
      lat: position.latitude,
      lng: position.longitude,
      accuracyM: position.accuracy ?? null,
      capturedAt: new Date().toISOString(),
    };

    canvas.toBlob(
      (blob) => {
        if (!blob) return;
        setCaptured({
          blob,
          previewUrl: URL.createObjectURL(blob),
          metadata,
          captureMode: "camera",
        });
      },
      "image/jpeg",
      JPEG_QUALITY,
    );
  };

  const pickFile = (file: File | undefined) => {
    if (!file || !position) return;
    setCaptured({
      blob: file,
      previewUrl: URL.createObjectURL(file),
      metadata: {
        lat: position.latitude,
        lng: position.longitude,
        accuracyM: position.accuracy ?? null,
        capturedAt: new Date().toISOString(),
      },
      captureMode: "fallback_upload",
    });
  };

  // ---- プレビュー ----
  if (captured) {
    return (
      <div className="fixed inset-0 z-50 flex flex-col bg-black md:mx-auto md:max-w-app md:border-x md:border-slate-800">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={captured.previewUrl}
          alt="撮影した画像のプレビュー"
          className="min-h-0 flex-1 object-contain"
        />
        <div className="space-y-3 bg-black px-4 pb-8 pt-4">
          <p className="text-center text-xs text-white/70">
            {captured.metadata.lat.toFixed(5)}, {captured.metadata.lng.toFixed(5)} ／{" "}
            {new Date(captured.metadata.capturedAt).toLocaleTimeString("ja-JP")}
          </p>
          <Button accent="worker" onClick={() => onSubmit(captured)} loading={submitting}>
            {submitting ? "送信しています…" : "撮影して送信"}
          </Button>
          <Button
            accent="neutral"
            disabled={submitting}
            onClick={() => {
              URL.revokeObjectURL(captured.previewUrl);
              setCaptured(null);
            }}
          >
            撮り直す
          </Button>
        </div>
      </div>
    );
  }

  // ---- カメラ（またはフォールバック） ----
  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-black md:mx-auto md:max-w-app md:border-x md:border-slate-800">
      <div className="relative min-h-0 flex-1">
        <video
          ref={videoRef}
          playsInline
          muted
          autoPlay
          className="h-full w-full bg-black object-cover"
        />
        <canvas ref={canvasRef} className="hidden" />

        <div className="absolute inset-x-0 top-0 flex items-center justify-between p-3">
          <button
            type="button"
            onClick={onClose}
            aria-label="閉じる"
            className="rounded-full bg-black/50 px-3 py-1.5 text-white"
          >
            ✕
          </button>
          <GpsBadge ready={gpsReady} accuracyM={position?.accuracy ?? null} />
          {torchAvailable ? (
            <button
              type="button"
              onClick={() => void toggleTorch()}
              aria-label="フラッシュ切替"
              className="rounded-full bg-black/50 px-3 py-1.5 text-white"
            >
              {torchOn ? "⚡️オン" : "⚡️オフ"}
            </button>
          ) : (
            <span className="w-12" />
          )}
        </div>

        <TimestampOverlay now={now} />

        {cameraError && (
          <div className="absolute inset-x-4 top-28 rounded-xl bg-amber-500/95 px-3 py-2 text-xs text-white">
            {cameraError}
          </div>
        )}

        {!gpsReady && (
          <div className="absolute inset-x-4 bottom-4 rounded-xl bg-red-600/95 px-3 py-2 text-center text-xs font-bold text-white">
            {geoError ?? "位置情報を有効にしてください"}
          </div>
        )}
      </div>

      <MetadataBar
        lat={position?.latitude ?? null}
        lng={position?.longitude ?? null}
        now={now}
        deviceLabel={deviceLabel()}
      />

      <div className="flex items-center justify-between px-8 py-6">
        <span className="text-[10px] font-bold text-white/60">{attemptLabel}</span>
        {cameraError ? (
          <label
            className={`rounded-xl px-4 py-3 text-xs font-bold ${
              gpsReady ? "bg-worker text-white" : "bg-white/20 text-white/40"
            }`}
          >
            ファイルを選択
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp"
              capture="environment"
              disabled={!gpsReady}
              className="hidden"
              onChange={(e) => pickFile(e.target.files?.[0])}
            />
          </label>
        ) : (
          <button
            type="button"
            onClick={shoot}
            disabled={!gpsReady}
            aria-label="撮影"
            className="h-16 w-16 rounded-full border-4 border-white bg-white transition disabled:border-white/30 disabled:bg-white/20"
          />
        )}
        <button
          type="button"
          onClick={() => setFacingMode(facingMode === "environment" ? "user" : "environment")}
          aria-label="カメラ切替"
          className="text-xl text-white/80"
        >
          🔄
        </button>
      </div>
    </div>
  );
}

function geolocationMessage(error: GeolocationPositionError): string {
  if (error.code === error.PERMISSION_DENIED) {
    return "位置情報の利用が拒否されました。設定から許可してください。";
  }
  if (error.code === error.POSITION_UNAVAILABLE) {
    return "位置情報を取得できませんでした。屋外で再試行してください。";
  }
  return "位置情報の取得がタイムアウトしました。";
}

function deviceLabel(): string {
  if (typeof navigator === "undefined") return "—";
  const ua = navigator.userAgent;
  if (/iPhone/.test(ua)) return "iPhone";
  if (/iPad/.test(ua)) return "iPad";
  if (/Android/.test(ua)) return "Android";
  if (/Macintosh/.test(ua)) return "Mac";
  if (/Windows/.test(ua)) return "Windows";
  return "その他";
}
