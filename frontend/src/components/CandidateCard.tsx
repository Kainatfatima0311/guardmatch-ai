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
 * assert a likelihood the number does not carry, and reviewers read a filled
 * ring as "83% suitable" no matter what the caption says.
 *
 * The words come before the numbers, because the plain-language layer is what a
 * non-technical reviewer reads and the twelve-row table is the audit trail
 * underneath it.
 */
export default function CandidateCard({ candidate }: { candidate: ScoredCandidate }) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const leading = candidate.rank === 1;

  return (
    <article
      className={clsx(
        "rounded-xl border bg-surface shadow-[var(--shadow)]",
        leading ? "border-primary" : "border-border",
      )}
    >
      <div className="flex flex-wrap items-start gap-x-4 gap-y-3 px-5 py-4">
        <span
          className={clsx(
            "tabular flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-sm font-semibold",
            leading
              ? "bg-primary text-primary-contrast"
              : "bg-surface-2 text-muted border border-border",
          )}
        >
          {candidate.rank}
          <span className="sr-only">
            {leading ? " — strongest fit for this posting" : ` of the shortlist`}
          </span>
        </span>

        <div className="min-w-0 flex-1">
          <h3 className="font-semibold tracking-tight">{candidate.candidate_id}</h3>
          <p className="tabular mt-0.5 text-sm text-muted">
            {candidate.relative_ranking_score > 0 ? "+" : ""}
            {candidate.relative_ranking_score.toFixed(4)}{" "}
            <span className="font-sans">relative ranking score — this posting only</span>
          </p>
        </div>

        <button
          type="button"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={() => setOpen((v) => !v)}
          className="rounded-lg border border-border-strong bg-surface-2 px-3 py-1.5 text-sm"
        >
          {open ? "Hide the numbers" : "Show the numbers"}
        </button>
      </div>

      <div className="border-t border-border px-5 py-4">
        <ReasonList reasons={candidate.explanation.reasons} />
      </div>

      {candidate.parse_warnings.length > 0 && (
        <div className="px-5 pb-4">
          <ParseWarnings warnings={candidate.parse_warnings} />
        </div>
      )}

      {open && (
        <div id={panelId} className="border-t border-border px-5 py-4">
          <ContributionBars
            explanation={candidate.explanation}
            score={candidate.relative_ranking_score}
          />
        </div>
      )}
    </article>
  );
}
