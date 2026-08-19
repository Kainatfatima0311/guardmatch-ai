import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import Shell from "@/components/Shell";
import "./globals.css";

/**
 * Fonts are self-hosted by `next/font`, which downloads the files at build time
 * and serves them from this origin. That matters here beyond performance: a
 * runtime request to a font CDN would put a third party in the request path of a
 * hiring tool and leak the fact that someone is using it. It also removes the
 * layout shift a late-arriving webfont causes.
 *
 * Inter for prose because it was designed for screen UI at small sizes, and
 * JetBrains Mono for figures because scores and contributions are read down a
 * column and compared, which needs tabular digits.
 */
const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-inter",
});

const mono = JetBrains_Mono({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-mono-face",
});

export const metadata: Metadata = {
  title: "GuardMatch — Rank workspace",
  description:
    "Rank security guard applicants against a job posting and see why each one landed where it did. A shortlisting aid, not a hiring decision.",
};

// Runs before first paint. Without it the page renders in the default theme and
// then repaints into the stored one, which reads as a flash of the wrong colour
// on every load. Inline and tiny for the same reason: an external file would be
// fetched after the first paint it exists to prevent.
const THEME_BOOTSTRAP = `
try {
  var t = localStorage.getItem("guardmatch-theme");
  if (t === "light" || t === "dark") document.documentElement.dataset.theme = t;
} catch (e) {}
`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${mono.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOTSTRAP }} />
      </head>
      <body>
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
