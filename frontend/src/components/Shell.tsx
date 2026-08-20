import type { ReactNode } from "react";
import { StatusProvider } from "@/lib/status";
import Rail from "./Rail";
import ThemeToggle from "./ThemeToggle";

/**
 * The page frame: a sidebar rail, a top bar, and the workspace.
 *
 * The disclaimer sits in the frame rather than on the results, so it cannot be
 * scrolled past or arrived at too late, and it is a bordered strip rather than
 * small print because small print is what readers have been trained to skip.
 *
 * THE RAIL IS NOT DUPLICATED FOR SMALL SCREENS
 *
 * Below `lg` it moves from a fixed column into a strip above the workspace,
 * carrying the same component. Two layouts means two things to keep in agreement,
 * and the rail holds status rather than navigation — there is nothing to collapse
 * into a menu, because there is one destination.
 *
 * A skip link comes first in the DOM. Without one, reaching the applications
 * means tabbing through the rail, nine certification chips and two selects on
 * every visit.
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
          <header className="sticky top-0 z-30 border-b border-border bg-surface/95 backdrop-blur">
            <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5 sm:px-6">
              <p className="flex min-w-0 items-start gap-2 rounded-lg border border-amber/30 bg-amber-surface px-3 py-2 text-xs leading-relaxed">
                <span aria-hidden="true" className="text-amber">
                  ✦
                </span>
                <span>
                  <span className="font-semibold text-amber">Shortlisting aid. </span>
                  <span className="text-text">
                    This orders a queue for a human reviewer. It does not reject candidates and
                    does not make hiring decisions.
                  </span>
                </span>
              </p>
              <ThemeToggle />
            </div>
          </header>

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
