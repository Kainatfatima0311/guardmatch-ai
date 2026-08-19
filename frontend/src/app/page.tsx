"use client";

import { useEffect, useMemo, useState } from "react";
import CandidateEditor, { validateCandidates } from "@/components/CandidateEditor";
import JobForm, { type JobDraft, type JobFormErrors } from "@/components/JobForm";
import RankResults from "@/components/RankResults";
import StatusFooter from "@/components/StatusFooter";
import { Button } from "@/components/ui";
import { rank, ready } from "@/lib/api";
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

  function loadSamples() {
    setJob({ ...SAMPLE_JOB, required_certifications: [...SAMPLE_JOB.required_certifications] });
    setCandidates(SAMPLE_CANDIDATES.map((c) => ({ ...c })));
    setResult(null);
    setError(null);
    setShowErrors(false);
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
        <div role="status" className="rounded-xl border border-amber/40 bg-amber-surface px-4 py-3">
          <p className="text-sm">
            <span className="font-medium text-amber">The scoring service is not ready. </span>
            {notReady}
          </p>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)] lg:items-start">
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
        />
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Button type="button" variant="primary" onClick={submit} disabled={busy}>
          {busy ? "Ranking…" : "Rank applications"}
        </Button>
        {showErrors && problems > 0 && (
          <p className="text-sm text-neg">
            {problems} thing{problems === 1 ? "" : "s"} to fix above.
          </p>
        )}
      </div>

      {/* One live region for every outcome, so a screen reader is told what
          happened once rather than having three regions compete. */}
      <div aria-live="polite" aria-atomic="false" className="flex flex-col gap-6">
        {busy && (
          <p className="text-sm text-muted">
            Parsing {candidates.length} application{candidates.length === 1 ? "" : "s"}, building
            features and computing explanations…
          </p>
        )}

        {error && !busy && (
          <div role="alert" className="rounded-xl border border-neg bg-surface p-4 shadow-[var(--shadow)]">
            <p className="font-medium text-neg">{error.title}</p>
            <p className="mt-1 text-sm text-muted">{error.detail}</p>
            {error.fieldErrors.length > 0 && (
              <ul className="mt-2 flex flex-col gap-1">
                {error.fieldErrors.map((f, i) => (
                  <li key={i} className="tabular text-xs text-muted">
                    {f.path || "request"} — <span className="font-sans">{f.message}</span>
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
            />
          </>
        )}

        {!result && !error && !busy && (
          <p className="text-sm text-muted">
            Nothing ranked yet. Fill in the posting and the applications, or press{" "}
            <span className="font-medium text-text">Load samples</span> to try it with four
            example CVs — one of them deliberately thin, so the difference between “the CV did
            not say” and “no” is visible.
          </p>
        )}
      </div>
    </div>
  );
}
