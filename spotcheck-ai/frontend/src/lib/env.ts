/**
 * 環境変数の読み込み口。
 * `process.env.NEXT_PUBLIC_*` をコンポーネントから直接参照せず、必ずここを経由する。
 */

export const env = {
  apiBaseUrl: process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
  googleMapsApiKey: process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY ?? "",
  defaultMapCenter: {
    lat: Number(process.env.NEXT_PUBLIC_DEFAULT_MAP_CENTER_LAT ?? "35.6595"),
    lng: Number(process.env.NEXT_PUBLIC_DEFAULT_MAP_CENTER_LNG ?? "139.7005"),
  },
} as const;

/** 未設定の環境変数を列挙する（起動時の警告表示用）。 */
export function missingEnvVars(): string[] {
  const missing: string[] = [];
  if (!process.env.NEXT_PUBLIC_API_BASE_URL) missing.push("NEXT_PUBLIC_API_BASE_URL");
  if (!env.googleMapsApiKey) missing.push("NEXT_PUBLIC_GOOGLE_MAPS_API_KEY");
  return missing;
}
