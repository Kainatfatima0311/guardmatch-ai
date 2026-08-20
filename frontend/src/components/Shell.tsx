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
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between gap-4 px-3 py-2 sm:px-4">
          <div className="flex min-w-0 items-center gap-3">
            {/* A mark rather than a logo: two bars reading as a ranked pair,
                which is the whole subject of the page. */}
            <span
              aria-hidden="true"
              className="flex h-6 w-6 shrink-0 flex-col items-center justify-center gap-0.5 rounded-sm bg-primary-wash"
            >
              <span className="block h-0.5 w-3 rounded-full bg-primary" />
              <span className="block h-0.5 w-2 rounded-full bg-primary opacity-55" />
            </span>
            <span className="text-sm font-semibold tracking-tight">GuardMatch</span>
          </div>
          <ThemeToggle />
        </div>

        {/* Tightened, but NOT shrunk. Everything else on this bar gave up a
            size for density; this is the one sentence that has to survive a
            partial read of the whole interface, so it keeps `text-xs` and only
            its padding moves. Making the disclaimer smaller to win vertical
            space would be spending the wrong thing. */}
        <div className="border-t border-border bg-amber-surface">
          <p className="mx-auto w-full max-w-6xl px-3 py-1.5 text-xs leading-relaxed sm:px-4">
            <span className="font-semibold text-amber">Shortlisting aid. </span>
            <span className="text-text">
              This orders a queue for a human reviewer. It does not reject candidates and does not
              make hiring decisions.
            </span>
          </p>
        </div>
      </header>

      <main id="workspace" className="mx-auto w-full max-w-6xl flex-1 px-3 py-5 sm:px-4">
        {children}
      </main>

      <footer className="mt-4 border-t border-border bg-surface">
        <div className="mx-auto flex w-full max-w-6xl flex-wrap items-center justify-between gap-x-6 gap-y-1 px-3 py-2.5 text-2xs text-muted sm:px-4">
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
