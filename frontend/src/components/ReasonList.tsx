/**
 * The plain-language layer, shown above the numbers.
 *
 * These sentences come from the service verbatim and are the layer a
 * non-technical reviewer actually reads, so they lead. They are generated under
 * two rules the API tests enforce: no probability language, and no raw
 * contribution figures — a "+0.94" shown to a reviewer reads as a percentage.
 *
 * Direction is stated in words here, which is the primary channel for it. The
 * colour and glyph in the contribution table are the redundant ones.
 *
 * The list can legitimately be empty. That happens when no single factor moved
 * the candidate away from the average, and the service replaces it with one
 * sentence saying so rather than leaving a blank.
 */
export default function ReasonList({
  reasons,
  dense,
}: {
  reasons: string[];
  /**
   * For a shortlist row rather than a detail panel: smaller type, a bullet in
   * place of a numbered chip, tighter leading.
   *
   * Every reason is still rendered. Showing only the first and hiding the rest
   * behind the disclosure was considered and rejected — these sentences are the
   * layer a non-technical reviewer actually reads, and a design that hides two
   * thirds of them to save height has traded away the thing it exists to show.
   * Density is bought by removing furniture, not by removing reasons.
   */
  dense?: boolean;
}) {
  if (reasons.length === 0) {
    return (
      <p className={dense ? "text-2xs text-muted" : "text-sm text-muted"}>
        No individual factor moved this candidate away from the average.
      </p>
    );
  }

  if (dense) {
    return (
      <ol className="flex flex-col gap-0.5">
        {reasons.map((reason, i) => (
          <li key={i} className="flex gap-1.5 text-2xs leading-relaxed text-muted">
            <span aria-hidden="true" className="shrink-0 text-border-strong">
              ·
            </span>
            <span>{reason}</span>
          </li>
        ))}
      </ol>
    );
  }

  return (
    <ol className="flex flex-col gap-2">
      {reasons.map((reason, i) => (
        <li key={i} className="flex gap-2.5 text-sm leading-relaxed">
          <span
            aria-hidden="true"
            className="tabular mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded bg-surface-3 text-2xs text-muted"
          >
            {i + 1}
          </span>
          <span>{reason}</span>
        </li>
      ))}
    </ol>
  );
}
