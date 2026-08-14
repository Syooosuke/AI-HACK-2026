/** カメラ画面のメタデータ表示（画面⑥）。GPS状態・タイムスタンプ・座標を重ねて表示する。 */

import { formatTime } from "@/lib/datetime";

export type CaptureMetadata = {
  lat: number;
  lng: number;
  accuracyM: number | null;
  /** シャッターを押した瞬間の時刻（ISO8601） */
  capturedAt: string;
};

export function GpsBadge({ ready, accuracyM }: { ready: boolean; accuracyM: number | null }) {
  return (
    <span
      className={`rounded-full px-2.5 py-1 text-[11px] font-bold ${
        ready ? "bg-worker text-white" : "bg-amber-500 text-white"
      }`}
    >
      {ready
        ? `GPS取得済${accuracyM != null ? `（±${Math.round(accuracyM)}m）` : ""}`
        : "GPS取得中"}
    </span>
  );
}

/**
 * 撮影時刻の焼き込み表示。
 *
 * 位置は置く側（CameraView の上部スタック）が決める。ここで absolute に置くと、
 * 同じ位置に出る他の帯（前回の指摘・カメラのエラー）と重なる。
 */
export function TimestampOverlay({ now }: { now: Date }) {
  return (
    <span className="rounded-lg bg-black/50 px-3 py-1 font-mono text-sm text-white">
      {now.toLocaleDateString("ja-JP")} {formatTime(now)}
    </span>
  );
}

export function MetadataBar({
  lat,
  lng,
  now,
  deviceLabel,
}: {
  lat: number | null;
  lng: number | null;
  now: Date;
  deviceLabel: string;
}) {
  return (
    <div className="grid grid-cols-4 gap-1 bg-black/70 px-3 py-2 text-center text-[10px] text-white">
      <Cell label="緯度" value={lat != null ? lat.toFixed(5) : "—"} />
      <Cell label="経度" value={lng != null ? lng.toFixed(5) : "—"} />
      <Cell label="時刻" value={formatTime(now)} />
      <Cell label="端末" value={deviceLabel} />
    </div>
  );
}

function Cell({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <p className="text-white/50">{label}</p>
      <p className="truncate font-mono">{value}</p>
    </div>
  );
}
