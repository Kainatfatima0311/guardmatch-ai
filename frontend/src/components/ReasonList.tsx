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
export default function ReasonList({ reasons }: { reasons: string[] }) {
  if (reasons.length === 0) {
    return (
      <p className="text-sm text-muted">
        No individual factor moved this candidate away from the average.
      </p>
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
