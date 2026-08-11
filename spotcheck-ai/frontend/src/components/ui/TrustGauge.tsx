/**
 * 0〜100 のスコアを見た目で伝えるゲージ（信頼度スコア / Reality Score 共用）。
 *
 * 「50.0 / 100」のような文字列ではなく、リングの埋まり具合と色で一目で分かるようにする。
 *   80以上 … 緑（pass） / 50以上 … 橙（warn） / 50未満 … 赤（fail） / 未算出 … 灰
 * 横に細く出したい場所（一覧の行など）では `TrustBar` を使う。
 */

const MAX_SCORE = 100;

/** リングの半径（viewBox 100×100 上の値）。 */
const RADIUS = 42;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

type Band = {
  /** この値以上で該当する下限 */
  min: number;
  color: string;
  label: string;
};

/** 上から順に判定する。色は tailwind.config.ts のトークンと同じ値。 */
const BANDS: Band[] = [
  { min: 80, color: "#10B981", label: "高い" },
  { min: 50, color: "#F59E0B", label: "標準" },
  { min: 0, color: "#EF4444", label: "要注意" },
];

const EMPTY_COLOR = "#CBD5E1"; // slate-300
const TRACK_COLOR = "#E2E8F0"; // slate-200

const SIZE_CLASS = {
  sm: "h-14 w-14",
  md: "h-20 w-20",
  lg: "h-28 w-28",
} as const;

const VALUE_CLASS = {
  sm: "text-sm",
  md: "text-xl",
  lg: "text-3xl",
} as const;

export type GaugeSize = keyof typeof SIZE_CLASS;

/** スコアを 0〜1 の比率へ丸める（範囲外の値が来ても崩れないようにする）。 */
function ratioOf(score: number): number {
  return Math.min(1, Math.max(0, score / MAX_SCORE));
}

function bandOf(score: number | null): Band | null {
  if (score == null) return null;
  return BANDS.find((band) => score >= band.min) ?? BANDS[BANDS.length - 1];
}

export function TrustGauge({
  score,
  label,
  size = "md",
  caption,
}: {
  /** 0〜100。未算出は null。 */
  score: number | null;
  /** ゲージが何のスコアかを示す見出し（読み上げにも使う）。 */
  label: string;
  size?: GaugeSize;
  caption?: string;
}) {
  const band = bandOf(score);
  const ratio = score == null ? 0 : ratioOf(score);

  return (
    <div className="flex flex-col items-center gap-1.5">
      <div
        className={`relative ${SIZE_CLASS[size]}`}
        role="meter"
        aria-valuemin={0}
        aria-valuemax={MAX_SCORE}
        aria-valuenow={score ?? undefined}
        aria-label={
          score == null ? `${label}: 未算出` : `${label}: ${MAX_SCORE}点中${score}点（${band?.label}）`
        }
      >
        <svg viewBox="0 0 100 100" className="h-full w-full -rotate-90">
          <circle
            cx="50"
            cy="50"
            r={RADIUS}
            fill="none"
            stroke={TRACK_COLOR}
            strokeWidth="11"
          />
          <circle
            cx="50"
            cy="50"
            r={RADIUS}
            fill="none"
            stroke={band?.color ?? EMPTY_COLOR}
            strokeWidth="11"
            strokeLinecap="round"
            strokeDasharray={CIRCUMFERENCE}
            strokeDashoffset={CIRCUMFERENCE * (1 - ratio)}
            className="transition-[stroke-dashoffset] duration-700 ease-out"
          />
        </svg>
        <span
          aria-hidden
          className="absolute inset-0 flex items-center justify-center font-bold tabular-nums text-slate-800"
        >
          <span className={VALUE_CLASS[size]}>{score == null ? "–" : Math.round(score)}</span>
        </span>
      </div>
      <span
        aria-hidden
        className="text-[11px] font-bold"
        style={{ color: band?.color ?? EMPTY_COLOR }}
      >
        {band?.label ?? "未算出"}
      </span>
      {caption && <span className="text-[11px] text-slate-500">{caption}</span>}
    </div>
  );
}

/** 一覧の行など、高さを取れない場所向けの横棒版。 */
export function TrustBar({
  score,
  label,
  className = "",
}: {
  score: number | null;
  label: string;
  className?: string;
}) {
  const band = bandOf(score);
  const ratio = score == null ? 0 : ratioOf(score);

  return (
    <span
      className={`inline-flex items-center gap-1.5 ${className}`}
      role="meter"
      aria-valuemin={0}
      aria-valuemax={MAX_SCORE}
      aria-valuenow={score ?? undefined}
      aria-label={score == null ? `${label}: 未算出` : `${label}: ${MAX_SCORE}点中${score}点`}
    >
      <span
        aria-hidden
        className="h-1.5 w-16 overflow-hidden rounded-full bg-slate-200"
      >
        <span
          className="block h-full rounded-full transition-[width] duration-700 ease-out"
          style={{ width: `${ratio * 100}%`, backgroundColor: band?.color ?? EMPTY_COLOR }}
        />
      </span>
      <span aria-hidden className="text-[11px] font-bold tabular-nums text-slate-500">
        {score == null ? "–" : Math.round(score)}
      </span>
    </span>
  );
}
