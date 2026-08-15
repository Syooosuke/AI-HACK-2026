/**
 * タブ間を移動したときに、直前の表示内容を一時的に保持するメモリキャッシュ。
 *
 * API の再取得は各画面で通常どおり行う。キャッシュはその待ち時間に前回の内容を
 * 表示してレイアウトのちらつきを防ぐためだけに使い、ブラウザ更新時には破棄する。
 */

import { getCurrentUser } from "@/lib/session";

const pageCache = new Map<string, unknown>();

function scopedKey(key: string): string | null {
  const user = getCurrentUser();
  return user ? `${user.id}:${key}` : null;
}

export function getPageCache<T>(key: string): T | undefined {
  const scoped = scopedKey(key);
  return scoped ? (pageCache.get(scoped) as T | undefined) : undefined;
}

export function setPageCache<T>(key: string, value: T): void {
  const scoped = scopedKey(key);
  if (scoped) pageCache.set(scoped, value);
}
