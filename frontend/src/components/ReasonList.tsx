/**
 * The plain-language layer, shown above the numbers.
 *
 * These sentences come from the backend verbatim and are the layer a
 * non-technical reviewer actually reads, so they lead. They are generated under
 * two rules the API tests enforce: no probability language, and no raw
 * contribution figures — a "+0.94" shown to a reviewer reads as a percentage.
 *
 * The list can legitimately be empty. That happens when no single factor moved
 * the candidate away from the average, and the backend replaces it with one
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
    <ul className="flex flex-col gap-1.5">
      {reasons.map((reason, i) => (
        <li key={i} className="flex gap-2 text-sm">
          <span aria-hidden="true" className="text-muted">
            •
          </span>
          <span>{reason}</span>
        </li>
      ))}
    </ul>
  );
}
