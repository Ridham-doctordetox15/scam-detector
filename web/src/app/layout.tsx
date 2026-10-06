import type { Metadata, Viewport } from "next";
import { Noto_Sans, Noto_Sans_Devanagari } from "next/font/google";
import type { ReactNode } from "react";
import { Providers } from "@/components/Providers";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";
import { en } from "@/i18n/en";
import { API_URL } from "@/lib/config";
import { buildCsp } from "@/lib/csp";
import "./globals.css";

// next/font downloads these at build time and serves them from this site, so visitors'
// browsers never contact Google. The Devanagari face isn't preloaded: its unicode-range means
// English-only pages never download it.
const notoSans = Noto_Sans({ subsets: ["latin"], variable: "--font-latin", display: "swap" });
const notoDeva = Noto_Sans_Devanagari({
  subsets: ["devanagari"],
  variable: "--font-deva",
  display: "swap",
  preload: false,
});

export const metadata: Metadata = {
  title: en.meta.title,
  description: en.meta.description,
  referrer: "no-referrer",
  robots: { index: true, follow: false },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  colorScheme: "light dark",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#fafafa" },
    { media: "(prefers-color-scheme: dark)", color: "#0b0d10" },
  ],
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    // suppressHydrationWarning: next-themes adds the `dark` class before React hydrates.
    <html lang="en" className={`${notoSans.variable} ${notoDeva.variable}`} suppressHydrationWarning>
      <head>
        <meta httpEquiv="Content-Security-Policy" content={buildCsp(API_URL)} />
      </head>
      <body className="min-h-dvh">
        <Providers>
          <div className="flex min-h-dvh flex-col">
            <SiteHeader />
            <main id="main" tabIndex={-1} className="flex-1 outline-none">
              {children}
            </main>
            <SiteFooter />
          </div>
        </Providers>
      </body>
    </html>
  );
}
