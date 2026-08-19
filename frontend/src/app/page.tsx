"use client";

import { useMemo, useState } from "react";
import CandidateEditor, { validateCandidates } from "@/components/CandidateEditor";
import JobForm, { type JobDraft, type JobFormErrors } from "@/components/JobForm";
import RankResults from "@/components/RankResults";
import { Button } from "@/components/ui";
import { rank } from "@/lib/api";
import type { NormalisedError } from "@/lib/errors";
import { SAMPLE_CANDIDATES, SAMPLE_JOB } from "@/lib/samples";
import type { Candidate, Job, RankResponse } from "@/lib/types";

/**
 * The Rank workspace.
 *
 * Holds the draft posting and the applications, validates what it can before
 * the network, and hands the result to the results view. Everything the API
 * would reject at the boundary — an unchosen shift pattern, a duplicate
 * reference, an oversized CV — is caught here first, so a 422 becomes a thing
 * that happens when the contract genuinely disagrees rather than the normal way
 * a reviewer discovers a limit.
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

type Status = "idle" | "submitting";

export default function Page() {
  const [job, setJob] = useState<JobDraft>(EMPTY_JOB);
  const [candidates, setCandidates] = useState<Candidate[]>(EMPTY_CANDIDATES);
  const [status, setStatus] = useState<Status>("idle");
  const [result, setResult] = useState<RankResponse | null>(null);
  const [error, setError] = useState<NormalisedError | null>(null);
  const [showErrors, setShowErrors] = useState(false);

  const candidateIssues = useMemo(() => validateCandidates(candidates), [candidates]);

  const jobErrors: JobFormErrors = useMemo(() => {
    const e: JobFormErrors = {};
    if (!job.shift_pattern) e.shift_pattern = "Choose the shift this role runs.";
    if (!job.site_type) e.site_type = "Choose the type of site.";
    if (!job.job_id.trim()) e.job_id = "Needs a reference.";
    return e;
  }, [job]);

  const blocked = candidateIssues.length > 0 || Object.keys(jobErrors).length > 0;
  const busy = status === "submitting";

  function loadSamples() {
    setJob({ ...SAMPLE_JOB, required_certifications: [...SAMPLE_JOB.required_certifications] });
    setCandidates(SAMPLE_CANDIDATES.map((c) => ({ ...c })));
    setResult(null);
    setError(null);
    setShowErrors(false);
  }

  async function submit() {
    setShowErrors(true);
    if (blocked) return;

    setStatus("submitting");
    setError(null);

    const response = await rank({
      // Safe: `blocked` is false, so both selects hold a real enum value.
      job: job as Job,
      candidates: candidates.map((c) => ({
        candidate_id: c.candidate_id.trim(),
        cv_text: c.cv_text,
      })),
    });

    if (response.ok) {
      setResult(response.data);
    } else {
      setError(response.error);
      setResult(null);
    }
    setStatus("idle");
  }

  return (
    <div className="flex flex-col gap-6">
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
        {showErrors && blocked && (
          <p className="text-sm text-neg">
            {candidateIssues.length + Object.keys(jobErrors).length} thing
            {candidateIssues.length + Object.keys(jobErrors).length === 1 ? "" : "s"} to fix
            above.
          </p>
        )}
      </div>

      {error && (
        <div
          role="alert"
          className="rounded-xl border border-neg bg-surface p-4 shadow-[var(--shadow)]"
        >
          <p className="font-medium text-neg">{error.title}</p>
          <p className="mt-1 text-sm text-muted">{error.detail}</p>
          {error.retryable && (
            <Button type="button" onClick={submit} className="mt-3">
              Try again
            </Button>
          )}
        </div>
      )}

      {result && <RankResults result={result} />}
    </div>
  );
}
