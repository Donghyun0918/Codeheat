import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CodeHeat 대시보드",
  description:
    "코드 복잡도/오너십 리포트를 트리맵 히트맵으로. 책임 추궁(blame)이 아니라 해결할 수 있는 사람 매칭.",
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
