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
 * particular way rather than for any visual reason:
 *
 *   All 12 features, always. The backend never truncates `contributions`, and
 *   dropping the ones that scored near zero would turn "this did not matter" into
 *   "this was not considered" — different claims a reader cannot tell apart from
 *   an absence.
 *
 *   Direction never depends on colour. Every row carries a sign and an arrow as
 *   well as the emerald or rose fill, so the information survives greyscale
 *   printing, a poor projector, and colour vision deficiency.
 *
 *   `null` renders as "not stated", never as 0. The parser distinguishes a fact
 *   the CV omitted from one it stated as zero, and so must this.
 *
 *   The sum is shown. SHAP here is additive — base value plus every contribution
 *   reconstructs the score — so the arithmetic is displayed and re-checked rather
 *   than asserted. An explanation that does not reconstruct the score it explains
 *   is a story printed beside a number.
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

  const inFavour = contributions.filter((c) => c.contribution > 0).length;
  const against = contributions.filter((c) => c.contribution < 0).length;
  const neutral = contributions.length - inFavour - against;

  return (
    <div className="flex flex-col gap-4">
      {/* Legend, so the axis is readable before any row is interpreted. */}
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-2xs">
        <span className="flex items-center gap-1.5 text-pos">
          <span aria-hidden="true">▲</span>
          <span className="tabular">{inFavour}</span>
          <span className="text-muted">in favour</span>
        </span>
        <span className="flex items-center gap-1.5 text-neg">
          <span aria-hidden="true">▼</span>
          <span className="tabular">{against}</span>
          <span className="text-muted">against</span>
        </span>
        {neutral > 0 && (
          <span className="flex items-center gap-1.5 text-muted">
            <span aria-hidden="true">→</span>
            <span className="tabular">{neutral}</span>
            <span>no effect</span>
          </span>
        )}
        <span className="ml-auto text-muted">
          all {contributions.length} factors, largest effect first
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-140 border-separate border-spacing-0 text-sm">
          <caption className="sr-only">
            Every feature the model used, with its value and its signed contribution to the score.
          </caption>
          <thead>
            <tr className="text-left text-2xs tracking-wide text-muted uppercase">
              <th scope="col" className="pb-2 font-medium">
                Factor
              </th>
              <th scope="col" className="pb-2 font-medium">
                Value
              </th>
              <th scope="col" className="pb-2 text-center font-medium">
                Against · In favour
              </th>
              <th scope="col" className="pb-2 text-right font-medium">
                Effect
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
                <tr key={c.feature} className="group">
                  <th
                    scope="row"
                    className="border-t border-border py-2.5 pr-4 text-left align-top font-normal"
                  >
                    <span className="flex flex-wrap items-baseline gap-x-1.5">
                      <span className="text-sm font-medium">{featureLabel(c.feature)}</span>
                      {meta?.proxy && (
                        <span
                          title={`Monitored proxy — ${meta.proxy}`}
                          className="cursor-help rounded bg-amber-surface px-1.5 py-0.5 text-2xs font-medium text-amber"
                        >
                          proxy
                        </span>
                      )}
                    </span>
                    {meta?.meaning && (
                      <span className="mt-0.5 block text-xs leading-snug text-muted">
                        {meta.meaning}
                      </span>
                    )}
                  </th>

                  <td
                    className={clsx(
                      "tabular border-t border-border py-2.5 pr-4 align-top text-xs whitespace-nowrap",
                      c.value === null ? "text-muted italic" : "text-text",
                    )}
                  >
                    {formatFeatureValue(c.value)}
                  </td>

                  <td className="border-t border-border py-2.5 pr-4 align-middle">
                    <div className="relative h-5 w-full" aria-hidden="true">
                      {/* The axis. A centre line rather than a left edge, because
                          these values are signed and a left-aligned bar would
                          make a large negative look like a large positive. */}
                      <div className="absolute inset-y-0 left-1/2 w-px bg-border-strong" />
                      {!zero && (
                        <div
                          className={clsx(
                            "absolute inset-y-1 rounded-sm",
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
                      "tabular border-t border-border py-2.5 text-right align-middle text-xs whitespace-nowrap",
                      zero ? "text-muted" : positive ? "text-pos" : "text-neg",
                    )}
                  >
                    <span aria-hidden="true" className="mr-1">
                      {zero ? "→" : positive ? "▲" : "▼"}
                    </span>
                    {formatContribution(c.contribution)}
                    <span className="sr-only">
                      {zero ? " — no effect" : positive ? " — counted in favour" : " — counted against"}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Presented as a result rather than a footnote. That the parts reconstruct
          the whole is the strongest claim this interface makes. */}
      <div
        className={clsx(
          "rounded-lg border px-4 py-3",
          additivity.holds ? "border-pos/35 bg-pos-wash" : "border-neg bg-neg-wash",
        )}
      >
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span aria-hidden="true" className={additivity.holds ? "text-pos" : "text-neg"}>
            {additivity.holds ? "✓" : "✗"}
          </span>
          <span className="text-sm font-semibold">
            {additivity.holds
              ? "The parts reconstruct the whole"
              : "This explanation does not account for its own score"}
          </span>
          <span className="text-xs text-muted">
            re-checked in your browser, not taken on trust
          </span>
        </div>
        <p className="tabular mt-2 text-xs leading-relaxed">
          <span className="text-muted">average </span>
          <span className="font-medium">{base_value.toFixed(4)}</span>
          <span className="text-muted"> + all {contributions.length} effects = </span>
          <span className="font-medium">{additivity.sum.toFixed(4)}</span>
          <span className="text-muted"> · reported </span>
          <span className="font-medium">{score.toFixed(4)}</span>
          <span className="text-muted"> · difference </span>
          <span className={additivity.holds ? "text-pos" : "text-neg"}>
            {additivity.delta.toExponential(1)}
          </span>
        </p>
      </div>
    </div>
  );
}
