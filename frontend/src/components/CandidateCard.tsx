"use client";

import clsx from "clsx";
import { useId, useState } from "react";
import type { ScoredCandidate } from "@/lib/types";
import ContributionBars from "./ContributionBars";
import ParseWarnings from "./ParseWarnings";
import ReasonList from "./ReasonList";

/**
 * One placement, with the reasons for it.
 *
 * The score is printed as a signed number next to its own name — no percentage,
 * no ring, no progress bar. A LambdaRank output is an ordering within one
 * posting; every visual idiom that suggests a proportion of something would
 * assert a likelihood the number does not carry, and reviewers read a filled ring
 * as "83% suitable" no matter what the caption says.
 *
 * The words come before the numbers, because the plain-language layer is what a
 * non-technical reviewer reads and the twelve-row table is the audit trail
 * underneath it.
 *
 * The leading candidate gets a heavier border and a filled rank badge. That is
 * hierarchy, not endorsement — the disclaimer above the list is what says what
 * being first does and does not mean.
 */
export default function CandidateCard({ candidate }: { candidate: ScoredCandidate }) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const leading = candidate.rank === 1;
  const score = candidate.relative_ranking_score;

  return (
    <article
      className={clsx(
        "overflow-hidden rounded-xl border bg-surface transition-shadow",
        leading
          ? "border-primary shadow-[var(--shadow-raised)]"
          : "border-border shadow-[var(--shadow-card)]",
      )}
    >
      <div className="flex flex-wrap items-center gap-x-4 gap-y-3 px-4 py-3.5 sm:px-5">
        <span
          className={clsx(
            "tabular flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-sm font-semibold",
            leading
              ? "bg-primary text-primary-contrast"
              : "border border-border-strong bg-surface-2 text-muted",
          )}
        >
          {candidate.rank}
          <span className="sr-only">
            {leading ? " — strongest fit for this posting" : " in the shortlist"}
          </span>
        </span>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-2">
            <h3 className="text-sm font-semibold tracking-tight">{candidate.candidate_id}</h3>
            {leading && (
              <span className="rounded bg-primary-wash px-1.5 py-0.5 text-2xs font-medium text-primary">
                strongest fit
              </span>
            )}
            {candidate.parse_warnings.length > 0 && (
              <span className="rounded bg-amber-surface px-1.5 py-0.5 text-2xs font-medium text-amber">
                {candidate.parse_warnings.length} gap
                {candidate.parse_warnings.length === 1 ? "" : "s"} in the CV
              </span>
            )}
          </div>
          <p className="mt-0.5 text-xs text-muted">
            <span className="tabular text-text">
              {score > 0 ? "+" : ""}
              {score.toFixed(4)}
            </span>{" "}
            relative ranking score — meaningful only within this posting, and not a probability
          </p>
        </div>

        <button
          type="button"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={() => setOpen((v) => !v)}
          className="rounded-lg border border-border-strong bg-surface-2 px-3 py-1.5 text-xs font-medium transition-colors hover:border-primary"
        >
          <span aria-hidden="true" className="mr-1.5">
            {open ? "▾" : "▸"}
          </span>
          {open ? "Hide the numbers" : "Show the numbers"}
        </button>
      </div>

      <div className="border-t border-border bg-surface-2 px-4 py-3.5 sm:px-5">
        <ReasonList reasons={candidate.explanation.reasons} />
      </div>

      {candidate.parse_warnings.length > 0 && (
        <div className="border-t border-border px-4 py-3 sm:px-5">
          <ParseWarnings warnings={candidate.parse_warnings} />
        </div>
      )}

      {open && (
        <div id={panelId} className="border-t border-border px-4 py-4 sm:px-5">
          <ContributionBars explanation={candidate.explanation} score={score} />
        </div>
      )}
    </article>
  );
}
