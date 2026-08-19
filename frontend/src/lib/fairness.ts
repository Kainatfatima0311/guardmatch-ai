import type { AttributeAudit, FairnessResponse } from "./types";

/**
 * Reading the audit correctly.
 *
 * The whole reason this module exists is one distinction that is easy to lose:
 * **`passes` is not `adverse_impact_ratio >= threshold`.**
 *
 * A ratio below the four-fifths line that is not distinguishable from noise after
 * correcting for the number of possible group comparisons is reported as
 * *inconclusive* rather than as a breach. The released `age_band` audit is exactly
 * that: a ratio of **0.627** against a threshold of 0.80, with `passes: true`.
 *
 * A dashboard that reads `passes` and draws a green tick would tell a reviewer
 * that age has been cleared, which the audit does not say. So no component reads
 * `passes` directly — they call `auditVerdict`, and there are three outcomes
 * rather than two.
 *
 * The history behind that third state is worth keeping in view. The first audit
 * run reported adverse impact of 0.627 on an attribute assigned at random, where
 * it could not possibly have influenced anything: a 319-member group had simply
 * landed low. A two-proportion z-test was not enough, because the ratio compares
 * the lowest group against the highest and those are chosen *because* they are
 * extreme. Bonferroni correction over the implied pairwise comparisons is what
 * turned a false alarm into an honest "cannot tell".
 */

export type Verdict = "pass" | "inconclusive" | "fail";

/**
 * The verdict for one attribute.
 *
 * Ordered deliberately: a failure outranks an inconclusive result, and an
 * inconclusive result outranks a pass. `passes` is consulted last, and only when
 * nothing else has been reported.
 */
export function auditVerdict(audit: AttributeAudit): Verdict {
  if (audit.failures.length > 0) return "fail";
  if (audit.inconclusive.length > 0) return "inconclusive";
  return audit.passes ? "pass" : "fail";
}

/** The verdict for the run as a whole, from the same three states. */
export function overallVerdict(report: FairnessResponse): Verdict {
  if (report.failures.length > 0) return "fail";
  if (report.inconclusive.length > 0) return "inconclusive";
  return report.passes ? "pass" : "fail";
}

/** What each verdict means, in words a reviewer can act on. */
export const VERDICT_LABEL: Record<Verdict, string> = {
  pass: "No disparity detected",
  inconclusive: "Cannot tell",
  fail: "Disparity detected",
};

export const VERDICT_DETAIL: Record<Verdict, string> = {
  pass: "Every measured ratio is within threshold on this data.",
  inconclusive:
    "A ratio is below threshold but not distinguishable from noise at this sample size. Neither cleared nor breached.",
  fail: "A measured ratio breaches its threshold and is statistically distinguishable from noise.",
};

/**
 * Whether the ratio itself is below the line, regardless of the verdict.
 *
 * Kept separate from the verdict on purpose: a reviewer should be able to see that
 * a number is low *and* that the audit will not draw a conclusion from it. Showing
 * only one of those is how "inconclusive" gets read as "fine".
 */
export function belowThreshold(audit: AttributeAudit, threshold: number): boolean {
  return audit.adverse_impact_ratio < threshold;
}

/**
 * Position of a ratio on a 0..1 bar, clamped.
 *
 * Ratios can exceed 1.0 when the compared groups invert, which is not a problem
 * but would otherwise draw a bar past its track.
 */
export function ratioPosition(ratio: number): number {
  return Math.max(0, Math.min(1, ratio));
}

/** Fixed four decimals, matching how the audit reports these elsewhere. */
export function formatRatio(value: number): string {
  return value.toFixed(4);
}

export function formatRate(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

/**
 * Groups sorted by selection rate, lowest first.
 *
 * The lowest group is the one the adverse impact ratio is computed from, so
 * leading with it puts the number being discussed at the top of the list.
 */
export function groupsByRate(audit: AttributeAudit): AttributeAudit["groups"] {
  return [...audit.groups].sort((a, b) => a.selection_rate - b.selection_rate);
}
