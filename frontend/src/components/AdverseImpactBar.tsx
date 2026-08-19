import clsx from "clsx";
import { formatRatio, ratioPosition, type Verdict } from "@/lib/fairness";

/**
 * The adverse impact ratio against its threshold.
 *
 * A bar with the threshold drawn on it, rather than a number beside a target,
 * because the question a reviewer has is "how far from the line" and that is a
 * distance rather than a value.
 *
 * The threshold marker is labelled with its own number. A line without a value is
 * a line someone has to be told about.
 *
 * A ratio below the line is **not** automatically drawn as a failure: the verdict
 * is passed in separately, because a ratio can sit below 0.80 and still be
 * inconclusive rather than a breach — which is the released `age_band` case at
 * 0.627. Colouring by position alone would call it a failure the audit does not
 * claim.
 */
export default function AdverseImpactBar({
  ratio,
  threshold,
  verdict,
}: {
  ratio: number;
  threshold: number;
  verdict: Verdict;
}) {
  const width = ratioPosition(ratio) * 100;
  const line = ratioPosition(threshold) * 100;

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-2xs tracking-wide text-muted uppercase">
          Adverse impact ratio
        </span>
        <span
          className={clsx(
            "tabular text-sm font-medium",
            verdict === "fail" && "text-neg",
            verdict === "inconclusive" && "text-amber",
            verdict === "pass" && "text-text",
          )}
        >
          {formatRatio(ratio)}
        </span>
      </div>

      <div className="relative h-2.5 w-full overflow-hidden rounded-full bg-surface-3">
        <div
          aria-hidden="true"
          className={clsx(
            "absolute inset-y-0 left-0 rounded-full",
            verdict === "fail" && "bg-neg",
            verdict === "inconclusive" && "bg-amber",
            verdict === "pass" && "bg-muted",
          )}
          style={{ width: `${width}%` }}
        />
        {/* The threshold, drawn over the bar so it reads as a line to clear
            rather than as part of the measurement. */}
        <div
          aria-hidden="true"
          className="absolute inset-y-0 w-0.5 bg-text"
          style={{ left: `${line}%` }}
        />
      </div>

      <p className="text-2xs text-muted">
        <span aria-hidden="true">│ </span>
        Four-fifths threshold {formatRatio(threshold)}
        {ratio < threshold && (
          <span className="text-amber"> · this ratio is below it</span>
        )}
      </p>
    </div>
  );
}
