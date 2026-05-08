import type { Metadata } from "next";
import "./globals.css";
import Shell from "@/components/Shell";

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || "https://stocks.magedzamzam.ae";
const TITLE = "Beacon Screener — DFM, ADX & EGX Stock Screener";
const DESCRIPTION =
  "Beacon Screener is a stock screener and portfolio coach for the MENA markets — Dubai (DFM), Abu Dhabi (ADX), and Egypt (EGX). Live broker quotes, fundamentals, technical indicators, and AI-driven Buy/Hold/Avoid verdicts.";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: TITLE,
    template: "%s · Beacon Screener",
  },
  description: DESCRIPTION,
  applicationName: "Beacon Screener",
  keywords: [
    "stock screener", "MENA stocks", "DFM", "ADX", "EGX",
    "Dubai stocks", "Abu Dhabi stocks", "Egypt stocks",
    "portfolio tracker", "Capital.com", "stock analysis",
    "Buy Hold Sell", "investment research",
  ],
  authors: [{ name: "Beacon Screener" }],
  manifest: "/manifest.json",
  // Next.js will auto-discover apple-touch-icon.png + icon-192.png + favicon-*.png
  // in /public, but we declare them explicitly so Safari/Edge can pin the right size.
  icons: {
    icon: [
      { url: "/favicon-32.png", sizes: "32x32", type: "image/png" },
      { url: "/icon-192.png", sizes: "192x192", type: "image/png" },
      { url: "/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
    apple: [{ url: "/apple-touch-icon.png", sizes: "180x180", type: "image/png" }],
    shortcut: "/favicon-32.png",
  },
  openGraph: {
    title: TITLE,
    description: DESCRIPTION,
    url: SITE_URL,
    siteName: "Beacon Screener",
    images: [
      {
        url: "/og.png",
        width: 1200,
        height: 630,
        alt: "Beacon Screener — Stock screener for DFM, ADX, and EGX",
      },
    ],
    locale: "en_US",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: TITLE,
    description: DESCRIPTION,
    images: ["/og.png"],
  },
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      "max-image-preview": "large",
      "max-snippet": -1,
    },
  },
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
