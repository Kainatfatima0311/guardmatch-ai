import { friendlyWarning } from "@/lib/warnings";

/**
 * What the parser could not find in a CV.
 *
 * The phrasings live in `@/lib/warnings` so they can be tested — including the
 * rule that none of them describes the applicant rather than the document.
 */
export default function ParseWarnings({ warnings }: { warnings: string[] }) {
  if (warnings.length === 0) return null;

  return (
    <div className="rounded-lg border border-border bg-surface-2 px-3 py-2.5">
      <p className="text-xs font-medium text-muted">
        The CV did not state {warnings.length} thing{warnings.length === 1 ? "" : "s"} the model
        looks for. These are gaps in the document, not findings about the applicant.
      </p>
      <ul className="mt-1.5 flex flex-col gap-1">
        {warnings.map((w, i) => (
          <li key={i} className="text-xs text-muted">
            <span aria-hidden="true">– </span>
            {friendlyWarning(w)}
          </li>
        ))}
      </ul>
    </div>
  );
}
