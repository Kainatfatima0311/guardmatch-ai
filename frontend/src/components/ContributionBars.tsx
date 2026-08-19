import clsx from "clsx";
import {
  FEATURES,
  checkAdditivity,
  featureLabel,
  formatContribution,
  formatFeatureValue,
} from "@/lib/features";
import type { Explanation } from "@/lib/types";

/**
 * The numeric record behind one placement.
 *
 * Four things this view has to get right, each because the model behaves a
 * particular way:
 *
 *   All 12 features, always. The backend never truncates `contributions`, and
 *   omitting the ones that scored near zero would turn "this did not matter"
 *   into "this was not considered" — different claims a reader cannot tell
 *   apart from an absence.
 *
 *   Direction never depends on colour. Every row carries a sign and an arrow as
 *   well as the emerald/rose fill, so the information survives greyscale, a
 *   projector, and the eight percent of men with a colour vision deficiency.
 *
 *   `null` renders as "not stated", never as 0. The parser distinguishes a fact
 *   the CV omitted from a fact it stated as zero, and so must this.
 *
 *   The sum is shown. SHAP here is additive — base value plus every
 *   contribution reconstructs the score — so the arithmetic is displayed and
 *   checked rather than asserted. An explanation that does not reconstruct the
 *   score it explains is a story printed beside a number.
 */
export default function ContributionBars({
  explanation,
  score,
}: {
  explanation: Explanation;
  score: number;
}) {
  const { base_value, contributions } = explanation;
  const additivity = checkAdditivity(base_value, contributions, score);
  const widest = Math.max(...contributions.map((c) => Math.abs(c.contribution)), 1e-9);

  return (
    <div className="flex flex-col gap-3">
      <div className="overflow-x-auto">
        <table className="w-full min-w-125 border-collapse text-sm">
          <caption className="sr-only">
            Every feature the model used, with its value and its signed contribution to the
            score.
          </caption>
          <thead>
            <tr className="text-left text-xs text-muted">
              <th scope="col" className="pb-2 font-medium">
                Factor
              </th>
              <th scope="col" className="pb-2 font-medium">
                Value
              </th>
              <th scope="col" className="pb-2 font-medium">
                Effect on the score
              </th>
              <th scope="col" className="pb-2 text-right font-medium">
                Contribution
              </th>
            </tr>
          </thead>
          <tbody>
            {contributions.map((c) => {
              const meta = FEATURES[c.feature];
              const width = (Math.abs(c.contribution) / widest) * 50;
              const positive = c.contribution > 0;
              const zero = c.contribution === 0;

              return (
                <tr key={c.feature} className="border-t border-border">
                  <th scope="row" className="py-2 pr-3 text-left font-normal align-top">
                    <span className="font-medium">{featureLabel(c.feature)}</span>
                    {meta?.proxy && (
                      <span
                        title={`Monitored proxy — ${meta.proxy}`}
                        className="ml-1.5 cursor-help text-xs text-muted"
                      >
                        (proxy)
                      </span>
                    )}
                    {meta?.meaning && (
                      <span className="block text-xs text-muted">{meta.meaning}</span>
                    )}
                  </th>

                  <td
                    className={clsx(
                      "tabular py-2 pr-3 align-top text-xs",
                      c.value === null ? "text-muted italic" : "",
                    )}
                  >
                    {formatFeatureValue(c.value)}
                  </td>

                  <td className="py-2 pr-3 align-top">
                    <div className="relative h-4 w-full" aria-hidden="true">
                      <div className="absolute inset-y-0 left-1/2 w-px bg-border-strong" />
                      {!zero && (
                        <div
                          className={clsx(
                            "absolute inset-y-0.5 rounded-sm",
                            positive ? "bg-pos" : "bg-neg",
                          )}
                          style={
                            positive
                              ? { left: "50%", width: `${width}%` }
                              : { right: "50%", width: `${width}%` }
                          }
                        />
                      )}
                    </div>
                  </td>

                  <td
                    className={clsx(
                      "tabular py-2 text-right align-top text-xs whitespace-nowrap",
                      zero ? "text-muted" : positive ? "text-pos" : "text-neg",
                    )}
                  >
                    <span aria-hidden="true">{zero ? "→" : positive ? "▲" : "▼"} </span>
                    {formatContribution(c.contribution)}
                    <span className="sr-only">
                      {zero
                        ? " — no effect"
                        : positive
                          ? " — counted in favour"
                          : " — counted against"}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="rounded-lg border border-border bg-surface-2 px-3 py-2.5 text-xs">
        <p className="text-muted">
          The parts reconstruct the whole. This is checked in the browser, not taken on trust.
        </p>
        <p className="tabular mt-1.5">
          <span className="text-muted">average </span>
          {base_value.toFixed(4)}
          <span className="text-muted"> + all 12 contributions = </span>
          <span className="font-medium">{additivity.sum.toFixed(4)}</span>
          <span className="text-muted"> vs reported </span>
          {score.toFixed(4)}
        </p>
        <p className={clsx("mt-1", additivity.holds ? "text-pos" : "text-neg")}>
          {additivity.holds
            ? `✓ Matches to ${additivity.delta.toExponential(1)}`
            : `✗ Off by ${additivity.delta.toExponential(1)} — this explanation does not account for its own score`}
        </p>
      </div>
    </div>
  );
}
