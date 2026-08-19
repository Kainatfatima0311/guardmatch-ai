import {
  auditVerdict,
  formatRate,
  formatRatio,
  groupsByRate,
} from "@/lib/fairness";
import type { AttributeAudit } from "@/lib/types";
import AdverseImpactBar from "./AdverseImpactBar";
import FairnessVerdict from "./FairnessVerdict";
import { Card, CardBody, CardHeader } from "./ui";

const LABELS: Record<string, string> = {
  gender: "Gender",
  age_band: "Age band",
  nationality: "Nationality",
};

/**
 * One protected attribute's audit.
 *
 * Four metrics, and each is here because the other three cannot see what it sees:
 *
 *   Adverse impact — the four-fifths rule. Unstable on small groups, which is why
 *   it is reported with a significance test rather than alone.
 *
 *   Demographic parity gap — the absolute difference in selection rates, which
 *   does not distort the way a ratio of two proportions does.
 *
 *   Equal opportunity gap — the same comparison restricted to candidates who were
 *   actually qualified, so a genuine difference in qualification does not read as
 *   discrimination.
 *
 *   Exposure ratio — the one that earns its place. Two groups shortlisted at
 *   exactly equal rates but placed 1-5 against 6-10 read as perfectly fair on
 *   every selection-rate metric above. Only exposure catches it.
 */
export default function AttributeAuditCard({
  audit,
  threshold,
  maxGap,
  minGroupSize,
}: {
  audit: AttributeAudit;
  threshold: number;
  maxGap: number;
  minGroupSize: number;
}) {
  const verdict = auditVerdict(audit);
  const groups = groupsByRate(audit);

  return (
    <Card>
      <CardHeader
        title={LABELS[audit.attribute] ?? audit.attribute}
        subtitle={`${audit.groups.length} groups compared at k = ${audit.top_k}`}
        actions={<FairnessVerdict verdict={verdict} />}
      />
      <CardBody className="flex flex-col gap-5">
        <AdverseImpactBar
          ratio={audit.adverse_impact_ratio}
          threshold={threshold}
          verdict={verdict}
        />

        {/* Why the verdict is what it is, in the audit's own words. Shown before
            the metrics, because a reviewer reading a number needs to know what
            conclusion is being drawn from it. */}
        {audit.inconclusive.length > 0 && (
          <div className="rounded-lg border border-amber/40 bg-amber-surface px-3.5 py-3">
            <p className="text-xs font-semibold text-amber">
              Below the threshold, and not conclusive
            </p>
            {audit.inconclusive.map((note, i) => (
              <p key={i} className="mt-1 text-xs leading-relaxed">
                {note}
              </p>
            ))}
            <p className="mt-2 text-xs leading-relaxed text-muted">
              A ratio compares the lowest group against the highest, and those are chosen
              <em> because</em> they are extreme. Testing a post-hoc extreme pair as though it
              were pre-specified inflates false positives, so the significance threshold is
              divided by the {audit.n_comparisons} possible comparisons
              {audit.n_comparisons > 1 && ` (${formatRatio(audit.significance_threshold)})`}.
              This is neither cleared nor breached.
            </p>
          </div>
        )}

        {audit.failures.length > 0 && (
          <div className="rounded-lg border border-neg bg-neg-wash px-3.5 py-3">
            <p className="text-xs font-semibold text-neg">Threshold breached</p>
            {audit.failures.map((note, i) => (
              <p key={i} className="mt-1 text-xs leading-relaxed">
                {note}
              </p>
            ))}
          </div>
        )}

        <div className="grid gap-x-6 gap-y-3 sm:grid-cols-3">
          <Metric
            label="Parity gap"
            value={formatRatio(audit.demographic_parity_gap)}
            limit={`max ${formatRatio(maxGap)}`}
            note="Absolute difference in selection rates. Does not distort on small groups the way a ratio does."
          />
          <Metric
            label="Equal opportunity gap"
            value={formatRatio(audit.equal_opportunity_gap)}
            limit={`max ${formatRatio(maxGap)}`}
            note="The same comparison among qualified candidates only, so a real difference in qualification is not read as discrimination."
          />
          <Metric
            label="Exposure ratio"
            value={formatRatio(audit.exposure_ratio)}
            limit="1.0 is equal"
            note="Position within the shortlist, not just admission to it. Two groups selected at equal rates but placed 1-5 against 6-10 look fair on every metric above; only this one catches it."
          />
        </div>

        <div className="overflow-x-auto">
          <table className="w-full min-w-120 border-separate border-spacing-0 text-sm">
            <caption className="sr-only">
              Per-group outcomes for {LABELS[audit.attribute] ?? audit.attribute}
            </caption>
            <thead>
              <tr className="text-left text-2xs tracking-wide text-muted uppercase">
                <th scope="col" className="pb-2 font-medium">
                  Group
                </th>
                <th scope="col" className="pb-2 text-right font-medium">
                  Appearances
                </th>
                <th scope="col" className="pb-2 text-right font-medium">
                  In top {audit.top_k}
                </th>
                <th scope="col" className="pb-2 text-right font-medium">
                  Selection rate
                </th>
                <th scope="col" className="pb-2 text-right font-medium">
                  Qualified rate
                </th>
                <th scope="col" className="pb-2 text-right font-medium">
                  Mean exposure
                </th>
              </tr>
            </thead>
            <tbody>
              {groups.map((g, i) => (
                <tr key={g.group}>
                  <th scope="row" className="border-t border-border py-2 pr-4 text-left font-normal">
                    <span className="font-medium">{g.group}</span>
                    {/* The ratio is computed from the extremes, so naming them
                        explains where the number came from. */}
                    {i === 0 && (
                      <span className="ml-1.5 text-2xs text-muted">lowest</span>
                    )}
                    {i === groups.length - 1 && groups.length > 1 && (
                      <span className="ml-1.5 text-2xs text-muted">highest</span>
                    )}
                  </th>
                  <td className="tabular border-t border-border py-2 text-right text-xs">
                    {g.n_appearances.toLocaleString()}
                  </td>
                  <td className="tabular border-t border-border py-2 text-right text-xs">
                    {g.n_in_top_k.toLocaleString()}
                  </td>
                  <td className="tabular border-t border-border py-2 text-right text-xs">
                    {formatRate(g.selection_rate)}
                  </td>
                  <td className="tabular border-t border-border py-2 text-right text-xs">
                    {formatRate(g.qualified_selection_rate)}
                  </td>
                  <td className="tabular border-t border-border py-2 text-right text-xs">
                    {formatRatio(g.mean_exposure)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {audit.suppressed_groups.length > 0 && (
          <p className="rounded-lg border border-border bg-surface-2 px-3.5 py-2.5 text-xs leading-relaxed text-muted">
            <span className="font-medium text-text">
              {audit.suppressed_groups.length} group
              {audit.suppressed_groups.length === 1 ? "" : "s"} suppressed
            </span>{" "}
            — fewer than {minGroupSize} appearances: {audit.suppressed_groups.join(", ")}. Reported
            as suppressed rather than omitted, because a metric computed on a handful of rows is
            noise presented as a finding, and silently dropping the group would hide that a group
            exists at all.
          </p>
        )}
      </CardBody>
    </Card>
  );
}

function Metric({
  label,
  value,
  limit,
  note,
}: {
  label: string;
  value: string;
  limit: string;
  note: string;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-2xs tracking-wide text-muted uppercase">{label}</span>
      <span className="tabular text-sm">
        {value} <span className="font-sans text-2xs text-muted">{limit}</span>
      </span>
      <span className="text-2xs leading-relaxed text-muted">{note}</span>
    </div>
  );
}
