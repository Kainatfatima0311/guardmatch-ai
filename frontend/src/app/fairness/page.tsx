"use client";

import { useEffect, useState } from "react";
import AttributeAuditCard from "@/components/AttributeAuditCard";
import FairnessVerdict from "@/components/FairnessVerdict";
import { Button, Card, CardBody, CardHeader, Stat } from "@/components/ui";
import { fairness } from "@/lib/api";
import type { NormalisedError } from "@/lib/errors";
import { overallVerdict, VERDICT_DETAIL } from "@/lib/fairness";
import type { FairnessResponse } from "@/lib/types";

/**
 * The fairness audit, on a screen.
 *
 * The audit runs offline, is written into the artifact bundle, and is enforced as
 * a CI gate on every push. Until this page it was readable only by opening a JSON
 * file or a report — which made the project's most consequential claim the one
 * least likely to be looked at.
 *
 * What this page must not become is a wall of green ticks. The model card's own
 * condition of use says *"Treat 0.80 as a floor, not a target"*, and the fairness
 * report records that a realistically-sized proxy bias **passed** at 0.875. A
 * dashboard reporting only passes would be worse than no dashboard, so the
 * limitations sit alongside the results rather than behind a link.
 */
export default function FairnessPage() {
  const [report, setReport] = useState<FairnessResponse | null>(null);
  const [error, setError] = useState<NormalisedError | null>(null);
  const [loading, setLoading] = useState(true);

  /** The retry path. No cancellation guard: a user pressing Try again is present. */
  async function load() {
    setLoading(true);
    setError(null);
    const response = await fairness();
    if (response.ok) setReport(response.data);
    else setError(response.error);
    setLoading(false);
  }

  // The mount path, which looks like `load` but is not: it carries a cancellation
  // guard, because a navigation away before the response arrives would otherwise
  // set state on an unmounted component. Keeping them separate is cheaper than a
  // shared function that has to be told which situation it is in.
  useEffect(() => {
    let cancelled = false;
    fairness().then((response) => {
      if (cancelled) return;
      if (response.ok) setReport(response.data);
      else setError(response.error);
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-2">
        <h1 className="text-xl font-semibold tracking-tight">Fairness audit</h1>
        <p className="max-w-3xl text-sm leading-relaxed text-muted">
          Measured on held-out rankings, joined to demographics at evaluation time only. The
          model never sees these attributes — they exist in a module the scoring path does not
          import, and a test fails the build if that changes.
        </p>
      </header>

      <div aria-live="polite" className="flex flex-col gap-6">
        {loading && (
          <div className="rounded-xl border border-border bg-surface px-4 py-3.5 text-sm text-muted">
            Loading the audit for the model being served…
          </div>
        )}

        {error && !loading && (
          <div
            role="alert"
            className="rounded-xl border border-neg bg-surface p-4 shadow-[var(--shadow-card)]"
          >
            <p className="flex items-center gap-2 font-semibold text-neg">
              <span aria-hidden="true">▲</span>
              {error.title}
            </p>
            <p className="mt-1.5 text-sm leading-relaxed text-muted">{error.detail}</p>
            {error.retryable && (
              <Button type="button" onClick={load} className="mt-3">
                Try again
              </Button>
            )}
          </div>
        )}

        {report && !loading && (
          <>
            <Card raised>
              <CardHeader
                title="Verdict"
                subtitle={`Model ${report.model_version}, shortlist depth k = ${report.top_k}`}
                actions={<FairnessVerdict verdict={overallVerdict(report)} />}
              />
              <CardBody className="flex flex-col gap-4">
                <p className="text-sm leading-relaxed">
                  {VERDICT_DETAIL[overallVerdict(report)]}
                </p>

                <div className="flex flex-wrap gap-x-8 gap-y-3">
                  <Stat label="Attributes audited" value={String(report.attributes.length)} mono />
                  <Stat label="Postings" value={report.n_postings.toLocaleString()} mono />
                  <Stat label="Ranked rows" value={report.n_rows.toLocaleString()} mono />
                  <Stat
                    label="Threshold"
                    value={report.adverse_impact_threshold.toFixed(2)}
                    mono
                  />
                  <Stat label="Min group size" value={String(report.min_group_size)} mono />
                </div>

                {/* The honest reading, next to the verdict rather than after it.
                    A reviewer who reads only this card should still leave with
                    the right impression. */}
                <div className="rounded-lg border border-amber/40 bg-amber-surface px-4 py-3.5">
                  <p className="text-sm font-semibold text-amber">
                    Passing is not evidence of fairness
                  </p>
                  <ul className="mt-2 flex flex-col gap-1.5 text-xs leading-relaxed">
                    <li>
                      During testing, a realistically-sized proxy bias — a night-availability gap
                      of 0.402, roughly what a real caring-responsibilities correlation looks like
                      — produced an adverse impact of <span className="tabular">0.875</span> and{" "}
                      <span className="font-medium">passed</span>. Detection needed roughly twice
                      that strength.
                    </li>
                    <li>
                      Every figure here is measured on <span className="font-medium">synthetic</span>{" "}
                      demographics. The audit proves the machinery works; it does not establish
                      real-world fairness.
                    </li>
                    <li>
                      <span className="tabular">0.80</span> is a floor, not a target. A ratio of
                      0.85 warrants investigation, not celebration.
                    </li>
                  </ul>
                </div>
              </CardBody>
            </Card>

            {report.attributes.map((audit) => (
              <AttributeAuditCard
                key={audit.attribute}
                audit={audit}
                threshold={report.adverse_impact_threshold}
                maxGap={report.max_gap}
                minGroupSize={report.min_group_size}
              />
            ))}
          </>
        )}
      </div>
    </div>
  );
}
