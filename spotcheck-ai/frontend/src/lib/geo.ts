/** 距離計算・座標フォーマット。 */

const EARTH_RADIUS_M = 6_371_000;
/** 徒歩の想定速度。画面⑤の所要時間の概算に使う（docs/05-frontend.md 画面⑤）。 */
export const WALKING_METERS_PER_MINUTE = 80;

export function haversineMeters(
  lat1: number,
  lng1: number,
  lat2: number,
  lng2: number,
): number {
  const toRad = (deg: number) => (deg * Math.PI) / 180;
  const dPhi = toRad(lat2 - lat1);
  const dLambda = toRad(lng2 - lng1);
  const a =
    Math.sin(dPhi / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLambda / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.sqrt(a));
}

export function formatDistance(km: number): string {
  return km < 1 ? `${Math.round(km * 1000)} m` : `${km.toFixed(1)} km`;
}

/** 「1.2 km（徒歩約15分）」の形式。徒歩80m/分で概算した値であることを示す。 */
export function formatDistanceWithWalk(km: number): string {
  const minutes = Math.max(1, Math.round((km * 1000) / WALKING_METERS_PER_MINUTE));
  return `${formatDistance(km)}（徒歩約${minutes}分）`;
}

export function formatCoords(lat: number, lng: number): string {
  return `${lat.toFixed(5)}, ${lng.toFixed(5)}`;
}
