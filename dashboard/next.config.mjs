/** @type {import('next').NextConfig} */
const nextConfig = {
  // 백엔드 없이 정적 export (Vercel/GitHub Pages 어디든 배포 가능).
  output: "export",
  images: { unoptimized: true },
};

export default nextConfig;
