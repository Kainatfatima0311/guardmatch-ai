import clsx from "clsx";

/**
 * The three-step header from the mockup.
 *
 * IT ADVERTISES PROGRESS AND GATES NOTHING
 *
 * A reviewer may fill the posting after dropping the CVs, or edit the posting
 * after ranking and rank again. Nothing here disables anything, and no step has
 * to be "completed" before the next is reachable. That is why the marks read as
 * *state* rather than as permission: a tick means this part is ready, not that it
 * has been signed off.
 *
 * The state is derived from what is actually true — whether the posting
 * validates, whether any application has text in it, whether a shortlist exists —
 * rather than from a counter the interface increments. A stepper that tracks its
 * own idea of progress drifts from the thing it claims to describe the moment a
 * reviewer works out of order, which is most of the time.
 */
export type StepState = "ready" | "current" | "waiting";

export interface Step {
  title: string;
  detail: string;
  state: StepState;
}

export default function Steps({ steps }: { steps: readonly Step[] }) {
  return (
    <ol className="flex flex-col overflow-hidden rounded-xl border border-border bg-surface shadow-[var(--shadow-card)] sm:flex-row">
      {steps.map((step, i) => (
        <li
          key={step.title}
          className={clsx(
            "flex min-w-0 flex-1 items-center gap-3 px-4 py-3",
            i > 0 && "border-t border-border sm:border-t-0 sm:border-l",
            step.state === "current" && "bg-primary-wash/60",
          )}
        >
          <span
            aria-hidden="true"
            className={clsx(
              "tabular flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-2xs font-semibold",
              step.state === "ready" && "bg-pos-wash text-pos",
              step.state === "current" && "bg-primary text-primary-contrast",
              step.state === "waiting" && "border border-border-strong bg-surface-2 text-muted",
            )}
          >
            {step.state === "ready" ? "✓" : i + 1}
          </span>
          <span className="min-w-0">
            <span className="block truncate text-sm font-medium">
              {step.title}
              <span className="sr-only">
                {step.state === "ready"
                  ? " — ready"
                  : step.state === "current"
                    ? " — next to do, though nothing is gated"
                    : " — nothing here yet"}
              </span>
            </span>
            <span className="block truncate text-xs text-muted">{step.detail}</span>
          </span>
        </li>
      ))}
    </ol>
  );
}
