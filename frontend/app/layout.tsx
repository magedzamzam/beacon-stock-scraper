import type { Metadata } from "next";
import "./globals.css";
import Shell from "@/components/Shell";

export const metadata: Metadata = {
  title: "Beacon Screener",
  description: "Stock screener & portfolio coach for DFM, ADX, and EGX",
  manifest: "/manifest.json",
};

export const viewport = {
  themeColor: "#0b0f17",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen">
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
