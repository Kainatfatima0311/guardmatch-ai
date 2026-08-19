import type { ReactNode } from "react";
import ThemeToggle from "./ThemeToggle";

/**
 * The page frame: header, content column, footer.
 *
 * The header carries the one sentence that has to survive every screenshot and
 * every partial read of this interface — that the tool orders a queue and does
 * not decide anything. Putting it in the frame rather than on the results means
 * it cannot be scrolled past or arrived at too late.
 *
 * A skip link comes first in the DOM. Without one, reaching the applications
 * means tabbing through nine certification chips and two selects on every visit.
 */
export default function Shell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#workspace"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded-lg focus:bg-primary focus:px-3 focus:py-2 focus:text-sm focus:text-primary-contrast"
      >
        Skip to the workspace
      </a>

      <header className="border-b border-border bg-surface">
        <div className="mx-auto flex w-full max-w-6xl flex-wrap items-start justify-between gap-4 px-4 py-4 sm:px-6">
          <div className="min-w-0">
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <span className="text-lg font-semibold tracking-tight">GuardMatch</span>
              <span className="text-sm text-muted">Rank workspace</span>
            </div>
            <p className="mt-1 max-w-2xl text-sm text-muted">
              Orders a shortlist for a human reviewer. It does not reject candidates and does
              not make hiring decisions.
            </p>
          </div>
          <ThemeToggle />
        </div>
      </header>

      <main id="workspace" className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6">
        {children}
      </main>

      <footer className="border-t border-border bg-surface">
        <div className="mx-auto w-full max-w-6xl px-4 py-4 text-sm text-muted sm:px-6">
          Scores are relative to a single posting and are not probabilities.
        </div>
      </footer>
    </div>
  );
}
