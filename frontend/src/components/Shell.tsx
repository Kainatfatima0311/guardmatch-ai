import type { ReactNode } from "react";

/**
 * The page frame: header, content column, footer.
 *
 * The header carries the one sentence that has to survive every screenshot and
 * every partial read of this interface — that the tool orders a queue and does
 * not decide anything. Putting it in the frame rather than on the results means
 * it cannot be scrolled past or arrived at too late.
 */
export default function Shell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-border bg-surface">
        <div className="mx-auto w-full max-w-6xl px-4 py-4 sm:px-6">
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="text-lg font-semibold tracking-tight">GuardMatch</span>
            <span className="text-sm text-muted">Rank workspace</span>
          </div>
          <p className="mt-1 text-sm text-muted">
            Orders a shortlist for a human reviewer. It does not reject candidates and does
            not make hiring decisions.
          </p>
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6">{children}</main>

      <footer className="border-t border-border bg-surface">
        <div className="mx-auto w-full max-w-6xl px-4 py-4 text-sm text-muted sm:px-6">
          Scores are relative to a single posting and are not probabilities.
        </div>
      </footer>
    </div>
  );
}
