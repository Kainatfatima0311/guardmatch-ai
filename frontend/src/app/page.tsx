"use client";

import { useEffect, useMemo, useState } from "react";
import CandidateEditor, { validateCandidates } from "@/components/CandidateEditor";
import JobForm, { type JobDraft, type JobFormErrors } from "@/components/JobForm";
import RankResults from "@/components/RankResults";
import StatusFooter from "@/components/StatusFooter";
import { Button } from "@/components/ui";
import { rank, ready, sampleCandidates } from "@/lib/api";
import type { NormalisedError } from "@/lib/errors";
import { SAMPLE_CANDIDATES, SAMPLE_JOB } from "@/lib/samples";
import type { Candidate, Job, RankResponse } from "@/lib/types";

/**
 * The Rank workspace.
 *
 * Holds the draft posting and the applications, validates what it can before the
 * network, and hands the result to the results view. Everything the API would
 * reject at the boundary — an unchosen shift pattern, a duplicate reference, an
 * oversized CV — is caught here first, so a 422 becomes what happens when the
 * contract genuinely disagrees rather than the normal way a reviewer discovers a
 * limit.
 *
 * Readiness is probed on mount rather than discovered on submit. The service
 * verifies its model's checksums at startup and refuses to serve if they fail, so
 * "not ready" is a state a reviewer can arrive into — and finding out after
 * filling in a posting and four CVs is a worse way to learn it.
 */

const EMPTY_JOB: JobDraft = {
  job_id: "j_1",
  required_certifications: [],
  min_years_experience: 0,
  shift_pattern: "",
  site_type: "",
  driving_required: false,
};

const EMPTY_CANDIDATES: Candidate[] = [{ candidate_id: "c_1", cv_text: "" }];

export default function Page() {
  const [job, setJob] = useState<JobDraft>(EMPTY_JOB);
  const [candidates, setCandidates] = useState<Candidate[]>(EMPTY_CANDIDATES);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<RankResponse | null>(null);
  const [error, setError] = useState<NormalisedError | null>(null);
  const [showErrors, setShowErrors] = useState(false);
  const [notReady, setNotReady] = useState<string | null>(null);
  const [loadingDataset, setLoadingDataset] = useState(false);
  const [generatedNote, setGeneratedNote] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    ready().then((response) => {
      if (cancelled) return;
      if (!response.ok) setNotReady(response.error.detail);
      else if (!response.data.ready) setNotReady(response.data.detail ?? "The model is loading.");
      else setNotReady(null);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const candidateIssues = useMemo(() => validateCandidates(candidates), [candidates]);

  const jobErrors: JobFormErrors = useMemo(() => {
    const e: JobFormErrors = {};
    if (!job.shift_pattern) e.shift_pattern = "Choose the shift this role runs.";
    if (!job.site_type) e.site_type = "Choose the type of site.";
    if (!job.job_id.trim()) e.job_id = "Needs a reference.";
    return e;
  }, [job]);

  const problems = candidateIssues.length + Object.keys(jobErrors).length;

  /**
   * Generated applications, so the ranking path can be tried at the volume the
   * brief describes. The service produces these without touching the model, so it
   * works even while the model is still verifying.
   */
  async function loadDataset(count: number) {
    setLoadingDataset(true);
    setError(null);

    const response = await sampleCandidates(count);

    if (response.ok) {
      setCandidates(response.data.candidates.map((c) => ({ ...c })));
      setResult(null);
      setShowErrors(false);
      // Rendered from the response rather than assumed, so the interface cannot
      // claim a provenance the service did not state.
      setGeneratedNote(
        `${response.data.count} ${response.data.source} applications, generated from seed ${response.data.seed}. Not real applicants.`,
      );
    } else {
      setError(response.error);
    }
    setLoadingDataset(false);
  }

  function loadSamples() {
    setJob({ ...SAMPLE_JOB, required_certifications: [...SAMPLE_JOB.required_certifications] });
    setCandidates(SAMPLE_CANDIDATES.map((c) => ({ ...c })));
    setResult(null);
    setError(null);
    setShowErrors(false);
    setGeneratedNote(null);
  }

  async function submit() {
    setShowErrors(true);
    if (problems > 0) return;

    setBusy(true);
    setError(null);

    const response = await rank({
      // Safe: `problems` is 0, so both selects hold a real enum value.
      job: job as Job,
      candidates: candidates.map((c) => ({
        candidate_id: c.candidate_id.trim(),
        cv_text: c.cv_text,
      })),
    });

    if (response.ok) {
      setResult(response.data);
      setNotReady(null);
    } else {
      setError(response.error);
      setResult(null);
    }
    setBusy(false);
  }

  return (
    <div className="flex flex-col gap-6">
      {notReady && (
        <div
          role="status"
          className="flex gap-3 rounded-xl border border-amber/40 bg-amber-surface px-4 py-3.5"
        >
          <span
            aria-hidden="true"
            className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-amber text-2xs font-bold text-amber"
          >
            !
          </span>
          <p className="text-sm leading-relaxed">
            <span className="font-semibold text-amber">The scoring service is not ready. </span>
            <span className="text-text">{notReady}</span>
          </p>
        </div>
      )}

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,23rem)_minmax(0,1fr)]">
        <JobForm
          value={job}
          errors={showErrors ? jobErrors : undefined}
          onChange={setJob}
          disabled={busy}
        />
        <CandidateEditor
          candidates={candidates}
          issues={showErrors ? candidateIssues : []}
          disabled={busy}
          onChange={setCandidates}
          onLoadSamples={loadSamples}
          onLoadDataset={loadDataset}
          loadingDataset={loadingDataset}
        />
      </div>

      {generatedNote && (
        <div
          role="status"
          className="flex gap-2.5 rounded-lg border border-amber/40 bg-amber-surface px-4 py-2.5"
        >
          <span aria-hidden="true" className="text-amber">
            ◈
          </span>
          <p className="text-xs leading-relaxed">
            <span className="font-semibold text-amber">Generated data. </span>
            <span className="text-text">{generatedNote}</span>
          </p>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-x-4 gap-y-3 rounded-xl border border-border bg-surface px-4 py-3.5 shadow-[var(--shadow-card)]">
        <span
          aria-hidden="true"
          className="tabular flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-primary-wash text-2xs font-semibold text-primary"
        >
          3
        </span>
        <Button type="button" variant="primary" onClick={submit} disabled={busy}>
          {busy ? "Ranking…" : "Rank applications"}
        </Button>
        {showErrors && problems > 0 ? (
          <p className="flex items-center gap-1.5 text-sm font-medium text-neg">
            <span aria-hidden="true">▲</span>
            {problems} thing{problems === 1 ? "" : "s"} to fix above.
          </p>
        ) : (
          <p className="text-xs text-muted">
            Parses each CV, builds twelve features, ranks, and explains every placement.
          </p>
        )}
      </div>

      {/* One live region for every outcome, so a screen reader is told what
          happened once rather than having three regions compete. */}
      <div aria-live="polite" className="flex flex-col gap-5">
        {busy && (
          <div className="rounded-xl border border-border bg-surface px-4 py-3.5 text-sm text-muted">
            Parsing {candidates.length} application{candidates.length === 1 ? "" : "s"}, building
            features and computing explanations…
          </div>
        )}

        {error && !busy && (
          <div
            role="alert"
            className="rounded-xl border border-neg bg-surface p-4 shadow-[var(--shadow-card)]"
          >
            <p className="flex items-center gap-2 font-semibold text-neg">
              <span aria-hidden="true">▲</span>
              {error.title}
            </p>
            <p className="mt-1.5 text-sm leading-relaxed text-muted">{error.detail}</p>
            {error.fieldErrors.length > 0 && (
              <ul className="mt-3 flex flex-col gap-1 rounded-lg bg-neg-wash px-3 py-2">
                {error.fieldErrors.map((f, i) => (
                  <li key={i} className="text-xs">
                    <span className="tabular text-neg">{f.path || "request"}</span>
                    <span className="text-muted"> — {f.message}</span>
                  </li>
                ))}
              </ul>
            )}
            {error.retryable && (
              <Button type="button" onClick={submit} className="mt-3">
                Try again
              </Button>
            )}
          </div>
        )}

        {result && !busy && (
          <>
            <RankResults result={result} />
            <StatusFooter
              modelVersion={result.model_version}
              requestId={result.request_id}
              candidateCount={result.candidates.length}
            />
          </>
        )}

        {!result && !error && !busy && (
          <div className="rounded-xl border border-dashed border-border-strong px-5 py-8 text-center">
            <p className="text-sm font-medium">Nothing ranked yet</p>
            <p className="mx-auto mt-1.5 max-w-xl text-sm leading-relaxed text-muted">
              Fill in the posting and the applications, or press{" "}
              <span className="font-medium text-text">Load samples</span> to try it with four
              example CVs. One of them is deliberately thin, so the difference between “the CV did
              not say” and “no” is visible rather than theoretical.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
