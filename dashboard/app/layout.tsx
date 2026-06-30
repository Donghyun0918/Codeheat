import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CodeHeat Dashboard",
  description:
    "Code complexity & ownership reports as a treemap heatmap. Matching, not blame.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
