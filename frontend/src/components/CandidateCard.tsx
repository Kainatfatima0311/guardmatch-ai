"use client";

import clsx from "clsx";
import { useId, useMemo, useState } from "react";
import {
  requirementBadge,
  requirementsFor,
  yearsFromGap,
  type Requirement,
} from "@/lib/requirements";
import type { Job, ScoredCandidate } from "@/lib/types";
import Avatar from "./Avatar";
import ContributionBars from "./ContributionBars";
import ParseWarnings from "./ParseWarnings";
import ReasonList from "./ReasonList";

/**
 * One placement, in the shape the supplied mockup asked for.
 *
 * TWO THINGS THE MOCKUP ASKED FOR THAT ARE NOT HERE
 *
 * `92 /100`. The model emits a relative ranking score within one posting. It is
 * not calibrated to a 0-100 scale, and `/100` reads as "92% suitable" whatever
 * caption sits beside it. The same large figure in the same position now carries
 * the real signed score, so the layout survives and the claim does not.
 *
 * "Strong match". The same match level considered and rejected earlier: the
 * training labels are graded 0-3, but the output has no calibration to those
 * grades, so any level shown would be a threshold this component invented. The
 * badge carries a counted fact instead — see `lib/requirements.ts`, which also
 * explains why an unstated value is never counted as a failure.
 *
 * The score gets no bar, no ring and no percentage. The contribution bars in the
 * expanded panel keep theirs, because a contribution really is a magnitude within
 * one explanation, measured against the largest in it.
 *
 * No medal either. The mockup marked the top three gold, silver and bronze; a
 * medal says a person won something, and the only available claim is that one CV
 * matched a posting's stated requirements more closely than another.
 */
export default function CandidateCard({
  candidate,
  job,
  displayName,
}: {
  candidate: ScoredCandidate;
  job: Job;
  displayName?: string;
}) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const leading = candidate.rank === 1;
  const score = candidate.relative_ranking_score;
  const label = displayName ?? candidate.candidate_id;

  const summary = useMemo(
    () => requirementsFor(job, candidate.explanation),
    [job, candidate.explanation],
  );
  const years = useMemo(() => {
    const gap = candidate.explanation.contributions.find((c) => c.feature === "exp_gap")?.value;
    return yearsFromGap(gap, job.min_years_experience);
  }, [candidate.explanation, job.min_years_experience]);

  const met = summary.requirements.filter((r) => r.state === "met");
  const outstanding = summary.requirements.filter((r) => r.state !== "met");

  return (
    <div
      className={clsx(
        "border-l-2 transition-colors",
        leading ? "border-l-primary bg-primary-wash/25" : "border-l-transparent",
      )}
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 px-3 py-3">
        <span
          className={clsx(
            "tabular w-5 shrink-0 text-right text-xs",
            leading ? "font-semibold text-primary" : "text-muted",
          )}
        >
          {candidate.rank}
          <span className="sr-only">
            {leading ? " — strongest fit for this posting" : " in the shortlist"}
          </span>
        </span>

        <Avatar name={label} />

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-2">
            <h3 className="truncate text-sm font-medium">{label}</h3>
            {displayName && (
              <span className="tabular text-2xs text-muted">{candidate.candidate_id}</span>
            )}
          </div>
          <p className="tabular mt-0.5 text-xs text-muted">
            {years === null ? "Experience not stated" : `${years} years experience`}
          </p>
        </div>

        <div className="flex shrink-0 flex-col items-end gap-1">
          <span className="tabular text-base font-semibold">
            {score > 0 ? "+" : ""}
            {score.toFixed(4)}
            <span className="sr-only">
              {" "}
              relative ranking score — meaningful only within this posting, and not a probability
            </span>
          </span>
          <span
            className={clsx(
              "rounded-full px-2 py-0.5 text-2xs font-medium",
              summary.unmet === 0 && summary.notStated === 0
                ? "bg-pos-wash text-pos"
                : "bg-surface-2 text-muted",
            )}
          >
            {requirementBadge(summary)}
          </span>
        </div>

        <button
          type="button"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={() => setOpen((v) => !v)}
          className="shrink-0 rounded-lg border border-border-strong px-2 py-1 text-2xs text-muted transition-colors hover:border-primary hover:text-text"
        >
          <span aria-hidden="true">{open ? "▾" : "▸"}</span>
          <span className="sr-only">
            {open ? "Hide" : "Show"} the breakdown for {label}
          </span>
        </button>
      </div>

      {open && (
        <div
          id={panelId}
          className="flex flex-col gap-4 border-t border-border bg-surface-2/50 px-3 py-3"
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <RequirementColumn title="Requirements met" items={met} tone="met" />
            <RequirementColumn
              title="Not met, or not stated"
              items={outstanding}
              tone="outstanding"
            />
          </div>

          <div>
            <h4 className="text-2xs font-medium tracking-[0.07em] text-muted uppercase">
              Why this placement
            </h4>
            <div className="mt-1.5">
              <ReasonList reasons={candidate.explanation.reasons} dense />
            </div>
          </div>

          {candidate.parse_warnings.length > 0 && (
            <ParseWarnings warnings={candidate.parse_warnings} />
          )}

          <ContributionBars explanation={candidate.explanation} score={score} />
        </div>
      )}
    </div>
  );
}

/**
 * One side of the breakdown.
 *
 * "Not met" and "not stated" share a column because both are things a reviewer
 * should look at, but they are **marked differently within it** — a cross for a
 * stated absence and a hollow circle for silence. Collapsing them into one mark
 * would undo the distinction `lib/requirements.ts` exists to preserve.
 */
function RequirementColumn({
  title,
  items,
  tone,
}: {
  title: string;
  items: Requirement[];
  tone: "met" | "outstanding";
}) {
  return (
    <div>
      <h4 className="text-2xs font-medium tracking-[0.07em] text-muted uppercase">{title}</h4>
      {items.length === 0 ? (
        <p className="mt-1.5 text-2xs text-muted">
          {tone === "met" ? "None of the stated requirements." : "Nothing outstanding."}
        </p>
      ) : (
        <ul className="mt-1.5 flex flex-col gap-1">
          {items.map((r) => (
            <li key={r.feature} className="flex gap-1.5 text-2xs leading-relaxed">
              <span
                aria-hidden="true"
                className={clsx(
                  "shrink-0",
                  r.state === "met" && "text-pos",
                  r.state === "unmet" && "text-neg",
                  r.state === "not-stated" && "text-muted",
                )}
              >
                {r.state === "met" ? "✓" : r.state === "unmet" ? "✕" : "○"}
              </span>
              <span>
                <span className="font-medium">{r.label}</span>
                <span className="sr-only">
                  {r.state === "met"
                    ? " — met"
                    : r.state === "unmet"
                      ? " — not met"
                      : " — the CV did not say"}
                </span>
                {r.detail && <span className="text-muted"> — {r.detail}</span>}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
