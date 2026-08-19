import type { ReactNode } from "react";
import ThemeToggle from "./ThemeToggle";

/**
 * The page frame: header, content column, footer.
 *
 * The header carries the one sentence that has to survive every screenshot and
 * every partial read of this interface — that the tool orders a queue and does
 * not decide anything. Putting it in the frame rather than on the results means
 * it cannot be scrolled past or arrived at too late. It is set as a bordered
 * strip rather than small print, because small print is the thing readers have
 * been trained to skip.
 *
 * A skip link comes first in the DOM. Without one, reaching the applications
 * means tabbing through nine certification chips and two selects on every visit.
 */
export default function Shell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#workspace"
        className="sr-only focus:not-sr-only focus:absolute focus:top-3 focus:left-3 focus:z-50 focus:rounded-lg focus:bg-primary focus:px-3 focus:py-2 focus:text-sm focus:font-medium focus:text-primary-contrast"
      >
        Skip to the workspace
      </a>

      <header className="sticky top-0 z-30 border-b border-border bg-surface/95 backdrop-blur">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
          <div className="flex min-w-0 items-center gap-3">
            {/* A mark rather than a logo: two bars reading as a ranked pair,
                which is the whole subject of the page. */}
            <span
              aria-hidden="true"
              className="flex h-8 w-8 shrink-0 flex-col items-center justify-center gap-1 rounded-lg bg-primary-wash"
            >
              <span className="block h-1 w-4 rounded-full bg-primary" />
              <span className="block h-1 w-2.5 rounded-full bg-primary opacity-55" />
            </span>
            <div className="flex min-w-0 flex-wrap items-baseline gap-x-2.5">
              <span className="text-base font-semibold tracking-tight">GuardMatch</span>
              <span className="text-xs text-muted">Rank workspace</span>
            </div>
          </div>
          <ThemeToggle />
        </div>

        <div className="border-t border-border bg-amber-surface">
          <p className="mx-auto w-full max-w-6xl px-4 py-2 text-xs leading-relaxed sm:px-6">
            <span className="font-semibold text-amber">Shortlisting aid. </span>
            <span className="text-text">
              This orders a queue for a human reviewer. It does not reject candidates and does not
              make hiring decisions.
            </span>
          </p>
        </div>
      </header>

      <main id="workspace" className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6">
        {children}
      </main>

      <footer className="mt-4 border-t border-border bg-surface">
        <div className="mx-auto flex w-full max-w-6xl flex-wrap items-center justify-between gap-x-6 gap-y-2 px-4 py-4 text-xs text-muted sm:px-6">
          <p>Scores are relative to a single posting and are not probabilities.</p>
          <p>
            Synthetic training data. Read the model card before drawing conclusions from any
            number here.
          </p>
        </div>
      </footer>
    </div>
  );
}
