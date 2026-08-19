import { friendlyWarning } from "@/lib/warnings";

/**
 * What the parser could not find in a CV.
 *
 * Every label describes something the *document* did not say, never something the
 * applicant lacks. The phrasings live in `@/lib/warnings` so they can be tested,
 * and one of those tests asserts the rule rather than the strings.
 *
 * The heading says "gaps in the document" for the same reason. A reviewer
 * skimming this block should not come away with an impression of the candidate.
 */
export default function ParseWarnings({ warnings }: { warnings: string[] }) {
  if (warnings.length === 0) return null;

  return (
    <div className="rounded-lg border border-border bg-surface-2 px-3.5 py-3">
      <p className="flex flex-wrap items-baseline gap-x-1.5 text-xs font-medium">
        <span aria-hidden="true" className="text-amber">
          ◌
        </span>
        <span>
          The CV did not state {warnings.length} thing{warnings.length === 1 ? "" : "s"} the model
          looks for.
        </span>
        <span className="font-normal text-muted">
          These are gaps in the document, not findings about the applicant.
        </span>
      </p>
      <ul className="mt-2 flex flex-wrap gap-1.5">
        {warnings.map((w, i) => (
          <li
            key={i}
            className="rounded-full border border-border-strong bg-surface px-2.5 py-1 text-2xs text-muted"
          >
            {friendlyWarning(w)}
          </li>
        ))}
      </ul>
    </div>
  );
}
