"use client";

import { useEffect, useState } from "react";
import { Button, Card, CardBody, CardHeader, Stat } from "@/components/ui";
import { featureImportance, modelInfo } from "@/lib/api";
import type { NormalisedError } from "@/lib/errors";
import { FEATURES, featureLabel } from "@/lib/features";
import type { FeatureImportanceResponse, ModelInfoResponse } from "@/lib/types";

/**
 * What model is running, and what it leans on.
 *
 * The brief's third condition is *"versioned model artifacts, not just a pickle
 * file floating around"*. The evidence for that has always been served by
 * `/model-info` and read by nobody, which is the same failure the fairness audit
 * had: a guarantee nobody looks at.
 *
 * It is not a hypothetical failure either. The released artifact spent eleven days
 * unable to load on Linux because its checksums were recorded over Windows line
 * endings, and every local run stayed green. A page that states plainly which
 * version is being served, and that its checksums verified, is what turns that
 * from a thing discovered by a CI archaeologist into a thing visible on arrival.
 */

/** The comparison is the point. 0.904 alone says nothing. */
const METRIC_ROWS = [
  { key: "ndcg_at_10", label: "NDCG@10", note: "Ranking quality at the shortlist depth" },
  { key: "ndcg_at_5", label: "NDCG@5", note: "The same, for a shorter shortlist" },
  { key: "mean_average_precision", label: "MAP", note: "Precision averaged over positions" },
  { key: "mean_reciprocal_rank", label: "MRR", note: "Where the first good candidate lands" },
] as const;

export default function ModelPage() {
  const [info, setInfo] = useState<ModelInfoResponse | null>(null);
  const [importance, setImportance] = useState<FeatureImportanceResponse | null>(null);
  const [error, setError] = useState<NormalisedError | null>(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    setError(null);
    const [i, imp] = await Promise.all([modelInfo(), featureImportance()]);
    if (i.ok) setInfo(i.data);
    else setError(i.error);
    if (imp.ok) setImportance(imp.data);
    setLoading(false);
  }

  useEffect(() => {
    let cancelled = false;
    Promise.all([modelInfo(), featureImportance()]).then(([i, imp]) => {
      if (cancelled) return;
      if (i.ok) setInfo(i.data);
      else setError(i.error);
      if (imp.ok) setImportance(imp.data);
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const metric = (key: string) => info?.metrics[`model_${key}`];
  const baseline = (key: string) => info?.metrics[`baseline_${key}`];
  const widest = importance ? Math.max(...importance.features.map((f) => f.share)) : 1;

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-2">
        <h1 className="text-xl font-semibold tracking-tight">Model</h1>
        <p className="max-w-3xl text-sm leading-relaxed text-muted">
          What is running right now, where it came from, and what it relies on. Read from the
          service rather than from the repository — the answer to “which model produced this
          score” has to come from the thing that produced it.
        </p>
      </header>

      <div aria-live="polite" className="flex flex-col gap-6">
        {loading && (
          <div className="rounded-xl border border-border bg-surface px-4 py-3.5 text-sm text-muted">
            Loading provenance. Feature importance is computed from a 200-CV sample on first
            request, so this takes about a second.
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

        {info && !loading && (
          <>
            <Card raised>
              <CardHeader
                title="Provenance"
                subtitle="Recorded at training time, and verified at every startup"
              />
              <CardBody className="flex flex-col gap-5">
                <div className="flex flex-wrap gap-x-8 gap-y-3">
                  <Stat label="Version" value={info.model_version} mono />
                  <Stat label="Trained" value={info.trained_at?.slice(0, 10) ?? "—"} mono />
                  <Stat label="Git SHA" value={info.git_sha?.slice(0, 12) ?? "—"} mono />
                  <Stat label="Generator" value={info.data_version ?? "—"} mono />
                  <Stat label="Features" value={String(info.feature_names.length)} mono />
                </div>

                <div className="rounded-lg border border-border bg-surface-2 px-4 py-3.5">
                  <p className="text-sm font-medium">Checksums verified</p>
                  <p className="mt-1 text-xs leading-relaxed text-muted">
                    This page is being served, which means every file in the artifact matched its
                    recorded SHA-256 at startup. Verification is not optional and startup fails
                    loudly on mismatch, so an instance serving an unverified model cannot answer
                    this request at all.
                  </p>
                  <p className="mt-2 text-xs leading-relaxed text-muted">
                    Recorded from a clean tree, so <span className="tabular">{info.git_sha?.slice(0, 12)}</span>{" "}
                    genuinely describes the code that produced the model. Training refuses to write
                    an artifact from uncommitted code.
                  </p>
                </div>
              </CardBody>
            </Card>

            <Card>
              <CardHeader
                title="Performance"
                subtitle="Against a twenty-line rule baseline, on 50 held-out postings"
              />
              <CardBody className="flex flex-col gap-4">
                {/* The comparison, not the number. 0.904 means nothing on its own —
                    the baseline is what shows machine learning earned its place. */}
                <div className="overflow-x-auto">
                  <table className="w-full min-w-120 border-separate border-spacing-0 text-sm">
                    <thead>
                      <tr className="text-left text-2xs tracking-wide text-muted uppercase">
                        <th scope="col" className="pb-2 font-medium">
                          Metric
                        </th>
                        <th scope="col" className="pb-2 text-right font-medium">
                          Rule baseline
                        </th>
                        <th scope="col" className="pb-2 text-right font-medium">
                          This model
                        </th>
                        <th scope="col" className="pb-2 text-right font-medium">
                          Difference
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {METRIC_ROWS.map((row) => {
                        const b = baseline(row.key);
                        const m = metric(row.key);
                        if (b === undefined || m === undefined) return null;
                        const delta = m - b;
                        return (
                          <tr key={row.key}>
                            <th
                              scope="row"
                              className="border-t border-border py-2 pr-4 text-left font-normal"
                            >
                              <span className="font-medium">{row.label}</span>
                              <span className="block text-2xs text-muted">{row.note}</span>
                            </th>
                            <td className="tabular border-t border-border py-2 text-right text-xs text-muted">
                              {b.toFixed(4)}
                            </td>
                            <td className="tabular border-t border-border py-2 text-right text-xs font-medium">
                              {m.toFixed(4)}
                            </td>
                            <td className="tabular border-t border-border py-2 text-right text-xs">
                              {delta >= 0 ? "+" : "−"}
                              {Math.abs(delta).toFixed(4)}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>

                <div className="rounded-lg border border-amber/40 bg-amber-surface px-4 py-3.5">
                  <p className="text-sm font-semibold text-amber">Read these as synthetic</p>
                  <p className="mt-1.5 text-xs leading-relaxed">
                    The baseline is a twenty-line hand-weighted rule with no learned parameters.
                    It is here because <span className="tabular">0.904</span> means nothing on its
                    own — the comparison is what shows the model earned its place. The measured
                    score also came out <span className="font-medium">above</span> the 0.75–0.85
                    band the design doc predicted, and the target was not moved afterwards. The
                    honest reading is that the synthetic task is easier than real hiring.
                  </p>
                </div>
              </CardBody>
            </Card>

            {importance && (
              <Card>
                <CardHeader
                  title="What the model leans on"
                  subtitle={`Mean absolute SHAP contribution over ${importance.sample_size} generated CVs`}
                />
                <CardBody className="flex flex-col gap-4">
                  <div className="flex flex-col gap-1.5">
                    {importance.features.map((f) => {
                      const meta = FEATURES[f.feature];
                      return (
                        <div key={f.feature} className="flex items-center gap-3">
                          <span className="w-44 shrink-0 truncate text-xs" title={featureLabel(f.feature)}>
                            {featureLabel(f.feature)}
                            {meta?.proxy && (
                              <span className="ml-1.5 text-2xs text-amber" title={meta.proxy}>
                                proxy
                              </span>
                            )}
                          </span>
                          <div className="h-2.5 min-w-0 flex-1 overflow-hidden rounded-full bg-surface-3">
                            <div
                              aria-hidden="true"
                              className={meta?.proxy ? "h-full rounded-full bg-amber" : "h-full rounded-full bg-primary"}
                              style={{ width: `${(f.share / widest) * 100}%` }}
                            />
                          </div>
                          <span className="tabular w-14 shrink-0 text-right text-xs">
                            {(f.share * 100).toFixed(1)}%
                          </span>
                        </div>
                      );
                    })}
                  </div>

                  {/* The two findings this view exists to surface. Neither is
                      visible from any single candidate's explanation. */}
                  <div className="rounded-lg border border-amber/40 bg-amber-surface px-4 py-3.5">
                    <p className="text-sm font-semibold text-amber">
                      The largest input is also the largest fairness exposure
                    </p>
                    <ul className="mt-2 flex flex-col gap-1.5 text-xs leading-relaxed">
                      <li>
                        <span className="font-medium">Shift availability</span> dominates — and
                        availability for night work correlates with caring responsibilities, and so
                        with gender. Nothing is wrong with the feature; night cover genuinely needs
                        people who can work nights. It is the route through which proxy
                        discrimination would arrive, and removing it would cost real ranking
                        quality. Bars marked <span className="text-amber">proxy</span> are the four
                        the blocklist monitors.
                      </li>
                      <li>
                        <span className="font-medium">Time since last role</span> contributes almost
                        nothing while proxying for career breaks, which correlate with parental
                        leave. A feature with demographic exposure and no predictive value is a free
                        removal.
                      </li>
                      <li>
                        Measured against a fixed reference posting, since every feature here is
                        pairwise. Figures can differ slightly from the model card, which averaged
                        over the full set of training postings.
                      </li>
                    </ul>
                  </div>
                </CardBody>
              </Card>
            )}
          </>
        )}
      </div>
    </div>
  );
}
