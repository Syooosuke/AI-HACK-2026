/** 日時の表示・入力変換。表示は日本時間、送信はISO8601（UTC付き）。 */

const DATE_TIME = new Intl.DateTimeFormat("ja-JP", {
  month: "numeric",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "Asia/Tokyo",
});

const TIME = new Intl.DateTimeFormat("ja-JP", {
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  timeZone: "Asia/Tokyo",
});

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return DATE_TIME.format(new Date(iso));
}

export function formatTime(date: Date): string {
  return TIME.format(date);
}

/** `<input type="datetime-local">` の値をISO8601へ変換する。 */
export function localInputToIso(value: string): string {
  return new Date(value).toISOString();
}

/** 現在時刻から `minutes` 後を `<input type="datetime-local">` の値に整形する。 */
export function isoToLocalInput(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(
    date.getHours(),
  )}:${pad(date.getMinutes())}`;
}

export function minutesFromNow(minutes: number): Date {
  return new Date(Date.now() + minutes * 60 * 1000);
}

/** 残り時間を「あと2時間30分」の形式で返す。 */
export function formatRemaining(iso: string): string {
  const diffMs = new Date(iso).getTime() - Date.now();
  if (diffMs <= 0) return "期限切れ";
  const totalMinutes = Math.floor(diffMs / 60000);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return hours > 0 ? `あと${hours}時間${minutes}分` : `あと${minutes}分`;
}

/** 経過時間を「3分前」「2時間前」のように返す（お知らせ一覧の表示用）。 */
export function formatRelative(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  if (diffMs < 60_000) return "たった今";
  const totalMinutes = Math.floor(diffMs / 60_000);
  if (totalMinutes < 60) return `${totalMinutes}分前`;
  const totalHours = Math.floor(totalMinutes / 60);
  if (totalHours < 24) return `${totalHours}時間前`;
  const totalDays = Math.floor(totalHours / 24);
  if (totalDays < 7) return `${totalDays}日前`;
  return formatDateTime(iso);
}
