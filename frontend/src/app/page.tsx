"use client";

import { useEffect, useMemo, useState } from "react";
import CandidateEditor, { validateCandidates } from "@/components/CandidateEditor";
import JobForm, { type JobDraft, type JobFormErrors } from "@/components/JobForm";
import RankResults from "@/components/RankResults";
import StatusFooter from "@/components/StatusFooter";
import Steps, { type Step } from "@/components/Steps";
import { Button, Card, CardHeader } from "@/components/ui";
import { rank, ready, sampleCandidates } from "@/lib/api";
import type { NormalisedError } from "@/lib/errors";
import { SAMPLE_CANDIDATES, SAMPLE_JOB } from "@/lib/samples";
import { toRequestCandidates, type CandidateDraft } from "@/lib/files";
import { displayNames } from "@/lib/shortlist";
import { usePublishStatus } from "@/lib/status";
import type { Job, RankResponse } from "@/lib/types";

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

const EMPTY_CANDIDATES: CandidateDraft[] = [{ candidate_id: "c_1", cv_text: "" }];

export default function Page() {
  const [job, setJob] = useState<JobDraft>(EMPTY_JOB);
  const [candidates, setCandidates] = useState<CandidateDraft[]>(EMPTY_CANDIDATES);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<RankResponse | null>(null);
  const [error, setError] = useState<NormalisedError | null>(null);
  const [showErrors, setShowErrors] = useState(false);
  const [notReady, setNotReady] = useState<string | null>(null);
  const [loadingDataset, setLoadingDataset] = useState(false);
  const [generatedNote, setGeneratedNote] = useState<string | null>(null);
  // Measured here rather than reported by the service, and labelled as a round
  // trip in the results for exactly that reason: calling it "processing time"
  // would attribute the network to the model.
  const [roundTripMs, setRoundTripMs] = useState<number | undefined>(undefined);

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

  // The rail displays what the workspace is holding; publishing it here keeps
  // the frame from having to own the workspace's state to describe it.
  const publish = usePublishStatus();
  useEffect(() => {
    publish({ applications: candidates.length, ranked: result?.candidates.length ?? null });
  }, [publish, candidates.length, result]);

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
   * Derived from what is true, not from a counter this page increments. A stepper
   * that keeps its own idea of progress drifts from reality the moment a reviewer
   * works out of order, which is most of the time. Nothing here gates anything.
   */
  const steps: Step[] = useMemo(() => {
    const postingReady = Object.keys(jobErrors).length === 0;
    const anyText = candidates.some((c) => c.cv_text.trim().length > 0);
    const filled = candidates.filter((c) => c.cv_text.trim().length > 0).length;
    return [
      {
        title: "The posting",
        detail: postingReady ? "Ready" : "What this vacancy actually needs",
        state: postingReady ? "ready" : "current",
      },
      {
        title: "The applications",
        detail: anyText ? `${filled} with text` : "Drop CVs, generate a batch, or paste",
        state: anyText ? "ready" : postingReady ? "current" : "waiting",
      },
      {
        title: "Rank",
        detail: result ? `${result.candidates.length} placed, with reasons` : "Ranked results and explanations",
        state: result ? "ready" : postingReady && anyText ? "current" : "waiting",
      },
    ];
  }, [jobErrors, candidates, result]);

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
    const startedAt = performance.now();

    const response = await rank({
      // Safe: `problems` is 0, so both selects hold a real enum value.
      job: job as Job,
      // The one place a draft becomes a payload. `displayName` and `fromFile` are
      // dropped here — see the note in @/lib/files on why the name must not travel.
      candidates: toRequestCandidates(candidates),
    });

    setRoundTripMs(performance.now() - startedAt);

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
    /* SPACING CARRIES THE GROUPING
       Every gap on this page used to be `gap-6`, which means the posting, the
       note describing what was just loaded into it, the button that acts on it
       and the results were all exactly as related to each other as any other
       pair — that is, the layout said nothing. Proximity is the cheapest
       grouping signal there is, and it was being spent on nothing.
       The outer gap separates regions; the inner one holds a region together.
       The ratio is what reads, not the absolute values — which is why the ratio
       survived the redesign and the absolute values did not: they were chosen for
       a looser design and would read as holes in this one. */
    <div className="flex flex-col gap-4 sm:gap-5">
      <Steps steps={steps} />

      {notReady && (
        <div
          role="status"
          className="flex gap-2.5 rounded-md border border-amber/40 bg-amber-surface px-3 py-2.5"
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

      {/* THREE COLUMNS, AS IN THE SUPPLIED MOCKUP
          Posting, then applications with the action beneath them, then the
          shortlist. The action sits in the applications column because that is
          what it acts on: a button under the thing it submits needs no
          explaining, and the mockup puts it there for the same reason.

          Three columns only from `xl`. Below that the shortlist takes the full
          width under a two-column top, because a results row carries a rank, an
          avatar, a name, its reasons and a score — squeezing all of that into a
          third of a 1024px screen makes every reason wrap to four lines. */}
      <div className="grid items-start gap-4 md:grid-cols-2 xl:grid-cols-[minmax(0,17rem)_minmax(0,1fr)_minmax(0,1.2fr)] xl:gap-5">
          <JobForm
            value={job}
            errors={showErrors ? jobErrors : undefined}
            onChange={setJob}
            disabled={busy}
          />
          {/* One column: what is being ranked, where it came from, and the
              act of ranking it. */}
          <div className="flex flex-col gap-3">
            <CandidateEditor
              candidates={candidates}
              issues={showErrors ? candidateIssues : []}
              disabled={busy}
              onChange={setCandidates}
              onLoadSamples={loadSamples}
              onLoadDataset={loadDataset}
              loadingDataset={loadingDataset}
            />

        {generatedNote && (
          <div
            role="status"
            className="flex gap-2 rounded-md border border-amber/40 bg-amber-surface px-3 py-2"
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

        {/* Step three was the one element on this page that was not a card:
            steps one and two were numbered sections and the act they lead to was
            a bare strip. The sequence broke at exactly the moment of the action,
            which is the last place a pattern should give way.

            Deliberately NOT sticky. The premise for making it so was that
            the mockup places it directly under the applications it submits, so
            it is now beside them rather than below the whole workspace. */}
        <Card>
          <CardHeader
            icon="▶"
            title="Rank applications"
            subtitle="Parses each CV, builds twelve features, ranks, and explains every placement."
            actions={
              <Button type="button" variant="primary" onClick={submit} disabled={busy}>
                {busy ? "Ranking…" : "Rank applications"}
              </Button>
            }
          />
          {/* Only present when something is wrong, so the card growing is itself
              the signal. A count that lives in a subtitle competes with prose;
              one that arrives as a new row does not. */}
          {showErrors && problems > 0 && (
            <div role="alert" className="px-3 py-2 sm:px-4">
              <p className="flex items-center gap-1.5 text-sm font-medium text-neg">
                <span aria-hidden="true">▲</span>
                {problems} thing{problems === 1 ? "" : "s"} to fix above.
              </p>
            </div>
          )}
            </Card>
          </div>

      {/* One live region for every outcome, so a screen reader is told what
          happened once rather than having three regions compete. */}
        <div aria-live="polite" className="flex flex-col gap-3 md:col-span-2 xl:col-span-1">
        {busy && (
          <div className="rounded-md border border-border bg-surface px-3 py-2.5 text-xs text-muted">
            Parsing {candidates.length} application{candidates.length === 1 ? "" : "s"}, building
            features and computing explanations…
          </div>
        )}

        {error && !busy && (
          <div
            role="alert"
            className="rounded-md border border-neg bg-surface p-3"
          >
            <p className="flex items-center gap-2 font-semibold text-neg">
              <span aria-hidden="true">▲</span>
              {error.title}
            </p>
            <p className="mt-1 text-xs leading-relaxed text-muted">{error.detail}</p>
            {error.fieldErrors.length > 0 && (
              <ul className="mt-2 flex flex-col gap-0.5 rounded-md bg-neg-wash px-2.5 py-1.5">
                {error.fieldErrors.map((f, i) => (
                  <li key={i} className="text-2xs">
                    <span className="tabular text-neg">{f.path || "request"}</span>
                    <span className="text-muted"> — {f.message}</span>
                  </li>
                ))}
              </ul>
            )}
            {error.retryable && (
              <Button type="button" onClick={submit} className="mt-2">
                Try again
              </Button>
            )}
          </div>
        )}

        {result && !busy && (
          <>
            <RankResults
              result={result}
              job={job as Job}
              names={displayNames(candidates)}
              roundTripMs={roundTripMs}
            />
            <StatusFooter
              modelVersion={result.model_version}
              requestId={result.request_id}
            />
          </>
        )}

        {!result && !error && !busy && (
          /* Left-aligned and short. A centred block in a dashed box reads as a
             placeholder waiting to be replaced; a line of text at the start of the
             column reads as the interface telling you where you are. */
          <div className="rounded-md border border-dashed border-border-strong px-3 py-4">
            <p className="text-xs font-medium">Nothing ranked yet</p>
            <p className="mt-1 max-w-2xl text-xs leading-relaxed text-muted">
              Fill in the posting and the applications, or press{" "}
              <span className="font-medium text-text">Load samples</span> to try it with four
              example CVs. One of them is deliberately thin, so the difference between “the CV did
              not say” and “no” is visible rather than theoretical.
            </p>
          </div>
        )}
      </div>
      </div>
    </div>
  );
}
