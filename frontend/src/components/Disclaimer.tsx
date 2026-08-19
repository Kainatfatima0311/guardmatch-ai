/**
 * The constraint on how this output may be used.
 *
 * The text is taken from the response body, never from a copy held here. The
 * backend ships `disclaimer` with every ranking on purpose — so the constraint
 * travels with the data rather than living only in documentation — and a second
 * copy in the client would be free to drift from it. If the backend's wording
 * changes, this changes with it, because there is nothing here to update.
 *
 * Amber is reserved for exactly this. Nothing else in the interface uses it.
 */
export default function Disclaimer({ text }: { text: string }) {
  return (
    <div className="flex gap-3 rounded-xl border border-amber/40 bg-amber-surface px-4 py-3">
      <span aria-hidden="true" className="mt-0.5 text-amber">
        ⚠
      </span>
      <p className="text-sm text-text">
        <span className="font-medium text-amber">Read this with the results. </span>
        {text}
      </p>
    </div>
  );
}
