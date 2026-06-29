import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CodeHeat 🔥 대시보드",
  description:
    "코드 복잡도/오너십 리포트를 트리맵 히트맵으로. 누가 쌌나(blame)가 아니라 누가 해결할 수 있나(매칭).",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
