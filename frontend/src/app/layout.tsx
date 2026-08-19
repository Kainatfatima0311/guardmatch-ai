import type { Metadata } from "next";
import Shell from "@/components/Shell";
import "./globals.css";

export const metadata: Metadata = {
  title: "GuardMatch — Rank workspace",
  description:
    "Rank security guard applicants against a job posting and see why each one landed where it did. A shortlisting aid, not a hiring decision.",
};

// Runs before first paint. Without it the page renders in the default theme and
// then repaints into the stored one, which reads as a flash of the wrong colour
// on every navigation. It is inline and tiny for the same reason: an external
// file would be fetched after the first paint it exists to prevent.
const THEME_BOOTSTRAP = `
try {
  var t = localStorage.getItem("guardmatch-theme");
  if (t === "light" || t === "dark") document.documentElement.dataset.theme = t;
} catch (e) {}
`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOTSTRAP }} />
      </head>
      <body>
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
