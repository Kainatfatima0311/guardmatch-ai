"use client";

import type { ReactNode } from "react";
import { StatusProvider, useWorkspaceStatus } from "@/lib/status";
import Rail from "./Rail";
import ThemeToggle from "./ThemeToggle";

/**
 * The page frame: a sidebar rail, a header, and the workspace.
 *
 * THE AMBER BANNER IS GONE, AND THAT WAS CHECKED BEFORE IT WENT
 *
 * A two-line amber block used to sit across the top of every screen saying that
 * this orders a queue and decides nothing. It was removed at the user's request,
 * and the guarantee it carried survives in four places without it: the rail's
 * persistent note, the service's own `disclaimer` rendered above the shortlist
 * from the response body, the footer, and the first row of every CSV export.
 *
 * It was redundant with the rail rather than load-bearing, and it was also the
 * largest thing on the page. A warning shown twice is read less carefully than
 * one shown once, so removing the duplicate is not a weakening of it.
 *
 * What replaces it is not decoration: the header now says what the page is and
 * which posting is being worked on. It deliberately carries **no count**, because
 * counts live in the rail, and one figure under two names on one screen is a
 * defect this project has already had to fix once.
 *
 * A skip link comes first in the DOM. Without one, reaching the applications
 * means tabbing through the rail and the posting form on every visit.
 */
export default function Shell({ children }: { children: ReactNode }) {
  return (
    <StatusProvider>
      <div className="min-h-screen lg:flex">
        <a
          href="#workspace"
          className="sr-only focus:not-sr-only focus:absolute focus:top-3 focus:left-3 focus:z-50 focus:rounded-lg focus:bg-primary focus:px-3 focus:py-2 focus:text-sm focus:font-medium focus:text-primary-contrast"
        >
          Skip to the workspace
        </a>

        <aside className="shrink-0 border-b border-border bg-surface lg:sticky lg:top-0 lg:h-screen lg:w-60 lg:border-r lg:border-b-0">
          <Rail />
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          <Header />

          <main id="workspace" className="flex-1 px-4 py-5 sm:px-6">
            {children}
          </main>

          <footer className="border-t border-border bg-surface">
            <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-1 px-4 py-3 text-2xs text-muted sm:px-6">
              <p>Scores are relative to a single posting and are not probabilities.</p>
              <p>
                Synthetic training data. Read the model card before drawing conclusions from any
                number here.
              </p>
            </div>
          </footer>
        </div>
      </div>
    </StatusProvider>
  );
}

/**
 * What the page is, and what is being worked on.
 *
 * The `h1` is here rather than in the workspace because the workspace is three
 * panels with their own headings and no single subject. The page had no `h1` at
 * all before this, which meant a screen reader's document outline started at a
 * level two.
 */
function Header() {
  const status = useWorkspaceStatus();

  return (
    <header className="sticky top-0 z-30 border-b border-border bg-surface/95 backdrop-blur">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 py-2.5 sm:px-6">
        <div className="min-w-0">
          <h1 className="truncate text-sm font-semibold tracking-tight">Rank a vacancy</h1>
          <p className="truncate text-2xs text-muted">
            {status.posting ? (
              <>
                Posting <span className="tabular font-medium text-text">{status.posting}</span>
                {status.ranked !== null && " · shortlist ready"}
              </>
            ) : (
              "Give the posting a reference to begin"
            )}
          </p>
        </div>
        <ThemeToggle />
      </div>
    </header>
  );
}
