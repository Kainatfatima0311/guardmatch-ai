import clsx from "clsx";
import { VERDICT_DETAIL, VERDICT_LABEL, type Verdict } from "@/lib/fairness";

/**
 * A verdict badge, and the colour choice behind it is deliberate.
 *
 * **A pass is not celebrated.** No green tick, no emerald fill — a pass renders in
 * muted neutral. That is not restraint for its own sake: the model card's own
 * condition of use says *"Treat 0.80 as a floor, not a target. An adverse impact
 * ratio of 0.85 warrants investigation, not celebration,"* and the fairness report
 * records that a realistically-sized proxy bias **passed** at 0.875. A confident
 * green tick would contradict the project's own position on what passing means.
 *
 * **Inconclusive is amber**, which is the token reserved for a constraint on how
 * the output may be used — and "the sample cannot distinguish this from noise" is
 * exactly such a constraint.
 *
 * **A failure is `--neg`.** That token already carries validation errors and
 * SHAP-negative contributions; the honest description of it across this interface
 * is "something adverse", not "a SHAP direction", and a fairness breach belongs in
 * that set.
 */
export default function FairnessVerdict({
  verdict,
  size = "md",
}: {
  verdict: Verdict;
  size?: "sm" | "md";
}) {
  const glyph = verdict === "fail" ? "▲" : verdict === "inconclusive" ? "◐" : "✓";

  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1.5 rounded-full border font-medium",
        size === "sm" ? "px-2 py-0.5 text-2xs" : "px-2.5 py-1 text-xs",
        verdict === "fail" && "border-neg bg-neg-wash text-neg",
        verdict === "inconclusive" && "border-amber/50 bg-amber-surface text-amber",
        // Muted on purpose. See the note above.
        verdict === "pass" && "border-border-strong bg-surface-2 text-muted",
      )}
      title={VERDICT_DETAIL[verdict]}
    >
      <span aria-hidden="true">{glyph}</span>
      {VERDICT_LABEL[verdict]}
    </span>
  );
}
