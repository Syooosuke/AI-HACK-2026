/**
 * 検品状況のポーリング間隔（段階的バックオフ）。
 *
 * 画像検品は実測30秒〜15分かかる（`spotcheck-ai/docs/04-ai-pipeline.md`）。
 * 一律で2秒間隔にすると無駄なリクエストが増え、一律で長くするとスタブモード
 * （数秒で終わる）の体験が悪くなるため、**経過時間に応じて間隔を広げる**。
 */

/** 経過時間（ミリ秒）ごとの待ち時間（ミリ秒）。閾値は昇順に並べる。 */
export const POLL_SCHEDULE: ReadonlyArray<{ untilMs: number; intervalMs: number }> = [
  // 最初の30秒は短く刻む（スタブモードならここで終わる）
  { untilMs: 30_000, intervalMs: 2_000 },
  // 次の1分は5秒間隔
  { untilMs: 90_000, intervalMs: 5_000 },
  // その後は15秒間隔
  { untilMs: 300_000, intervalMs: 15_000 },
  // 5分以降は30秒間隔
  { untilMs: Number.POSITIVE_INFINITY, intervalMs: 30_000 },
];

/** 自動更新を打ち切るまでの時間。検品の実測上限（15分）に合わせる。 */
export const MAX_POLL_MS = 15 * 60_000;

/** 経過時間から次の待ち時間を返す。 */
export function nextPollInterval(elapsedMs: number): number {
  const step = POLL_SCHEDULE.find((entry) => elapsedMs < entry.untilMs);
  return step ? step.intervalMs : POLL_SCHEDULE[POLL_SCHEDULE.length - 1].intervalMs;
}

/** 打ち切り時間に達したか。 */
export function shouldStopPolling(elapsedMs: number): boolean {
  return elapsedMs >= MAX_POLL_MS;
}

/** 「1分20秒」のような表示にする（待機中の経過時間表示に使う）。 */
export function formatElapsed(elapsedMs: number): string {
  const totalSeconds = Math.floor(elapsedMs / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes === 0) return `${seconds}秒`;
  return seconds === 0 ? `${minutes}分` : `${minutes}分${seconds}秒`;
}
