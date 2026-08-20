"use client";

import clsx from "clsx";
import { useId, useState } from "react";
import type { ScoredCandidate } from "@/lib/types";
import ContributionBars from "./ContributionBars";
import ParseWarnings from "./ParseWarnings";
import ReasonList from "./ReasonList";

/**
 * One placement, as a row.
 *
 * It used to be a card: a header strip, a filled band of reasons, a warnings
 * band, and padding on all of it. Read once that is fine; read two hundred and
 * fifty times it is furniture. This is the same information in a row that shares
 * one frame with its neighbours.
 *
 * THE SCORE STILL GETS NO BAR
 *
 * A dense table invites one more than a card ever did — a column of numbers looks
 * unfinished without a sparkline beside it. It does not get one. A LambdaRank
 * output is an ordering within a single posting; every proportional idiom asserts
 * a likelihood the number does not carry, and a reviewer reads a filled bar as
 * "83% suitable" whatever the caption says. The contribution bars in the expanded
 * panel keep theirs, because a contribution really is a magnitude within one
 * explanation, measured against the largest one in it.
 *
 * WHAT MOVED, AND WHAT DID NOT
 *
 * The caveat that used to sit under every score — "meaningful only within this
 * posting, and not a probability" — is now the score column's header, stated once
 * for the table instead of two hundred and fifty times down it. It is still
 * present for a screen reader on every row, because a row read aloud on its own
 * has no column header.
 *
 * Every reason still renders. Density comes from removing furniture, not from
 * hiding the plain-language layer this project exists to provide.
 */
export default function CandidateCard({
  candidate,
  displayName,
}: {
  candidate: ScoredCandidate;
  displayName?: string;
}) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const leading = candidate.rank === 1;
  const score = candidate.relative_ranking_score;
  const gaps = candidate.parse_warnings.length;

  return (
    <div
      className={clsx(
        "border-l-2 transition-colors",
        leading ? "border-l-primary" : "border-l-transparent",
      )}
    >
      <div className="flex items-start gap-2.5 px-2.5 py-2 sm:gap-3 sm:px-3">
        <span
          className={clsx(
            "tabular w-5 shrink-0 pt-px text-right text-2xs",
            leading ? "font-semibold text-primary" : "text-muted",
          )}
        >
          {String(candidate.rank).padStart(2, "0")}
          <span className="sr-only">
            {leading ? " — strongest fit for this posting" : " in the shortlist"}
          </span>
        </span>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
            <h3 className="truncate text-xs font-medium">
              {displayName ?? candidate.candidate_id}
            </h3>
            {displayName && (
              <span className="tabular text-2xs text-muted">{candidate.candidate_id}</span>
            )}
            {gaps > 0 && (
              <span className="rounded-sm bg-amber-surface px-1 py-px text-2xs font-medium text-amber">
                {gaps} unstated
              </span>
            )}
          </div>
          <div className="mt-1">
            <ReasonList reasons={candidate.explanation.reasons} dense />
          </div>
        </div>

        <span className="tabular shrink-0 pt-px text-xs">
          {score > 0 ? "+" : ""}
          {score.toFixed(4)}
          <span className="sr-only">
            {" "}
            relative ranking score — meaningful only within this posting, and not a probability
          </span>
        </span>

        <button
          type="button"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={() => setOpen((v) => !v)}
          className="shrink-0 px-1 text-2xs text-muted transition-colors hover:text-text"
        >
          <span aria-hidden="true">{open ? "▾" : "▸"}</span>
          <span className="sr-only">
            {open ? "Hide" : "Show"} the twelve contributions for{" "}
            {displayName ?? candidate.candidate_id}
          </span>
        </button>
      </div>

      {open && (
        <div id={panelId} className="border-t border-border bg-surface-2 px-2.5 py-3 sm:px-3">
          {gaps > 0 && (
            <div className="mb-3">
              <ParseWarnings warnings={candidate.parse_warnings} />
            </div>
          )}
          <ContributionBars explanation={candidate.explanation} score={score} />
        </div>
      )}
    </div>
  );
}
