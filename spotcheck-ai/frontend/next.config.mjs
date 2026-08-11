/** @type {import('next').NextConfig} */
const nextConfig = {
  // Cloud Run 用に、実行に必要なファイルだけを .next/standalone へ出力する
  output: "standalone",
};

export default nextConfig;
