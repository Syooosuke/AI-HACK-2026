import type { Config } from "tailwindcss";

/**
 * デザイントークン（docs/05-frontend.md 1節）。
 * クライアント側は青系、ワーカー側は緑系、AI判定・安全処理は紫系で区別する。
 */
const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // 役割ごとのアクセント
        client: "#2563EB", // blue-600
        worker: "#059669", // emerald-600
        ai: "#7C3AED", // violet-600
        // 判定結果
        pass: "#10B981", // emerald-500
        fail: "#EF4444", // red-500
        warn: "#F59E0B", // amber-500
      },
      borderRadius: {
        card: "1rem", // rounded-2xl 相当をカードの既定に
      },
      maxWidth: {
        // モバイルファースト。デスクトップでもこの幅で中央寄せする
        app: "28rem",
      },
    },
  },
  plugins: [],
};
export default config;
