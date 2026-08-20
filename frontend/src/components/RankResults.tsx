"use client";

import { useMemo, useState } from "react";
import {
  NO_FILTERS,
  SORT_LABELS,
  applyFilters,
  csvFilename,
  filtersActive,
  sortCandidates,
  toCsv,
  type ShortlistFilters,
  type SortKey,
} from "@/lib/shortlist";
import type { RankResponse } from "@/lib/types";
import CandidateCard from "./CandidateCard";
import Disclaimer from "./Disclaimer";
import { Button, Chip, Select, TextInput } from "./ui";

/**
 * The shortlist.
 *
 * Order comes from the service. Ties are already broken deterministically by
 * candidate id server-side, so two identical applications keep a stable order
 * rather than drifting with upload position.
 *
 * The disclaimer sits above the list rather than below it. Below, it is a footnote
 * to a decision already formed; above, it is a condition on reading what follows.
 *
 * FILTERING IS A WAY OF READING, NOT A WAY OF RANKING
 *
 * Every control here changes the view and nothing else. Ranks are never
 * renumbered, so row one of a filtered list still reports its real position — and
 * the count states plainly how many of the total are showing, because a reviewer
 * who narrows to twelve of two hundred and fifty needs to know they are looking at
 * positions from the full set.
 *
 * The export is deliberately the exception: it writes the **whole** shortlist. A
 * file named "shortlist" that silently held a fifth of one would be a different
 * document wearing the same name.
 */
export default function RankResults({
  result,
  names,
}: {
  result: RankResponse;
  names?: Map<string, string>;
}) {
  const [filters, setFilters] = useState<ShortlistFilters>(NO_FILTERS);
  const [sort, setSort] = useState<SortKey>("rank");

  // Memoised because it feeds a `useMemo` dependency list. Left as a bare `??`,
  // a fresh Map every render would defeat the memo it is a dependency of — the
  // filter and sort would re-run on every keystroke elsewhere in the tree.
  const labels = useMemo(() => names ?? new Map<string, string>(), [names]);
  const withGaps = result.candidates.filter((c) => c.parse_warnings.length > 0).length;
  const isLong = result.candidates.length > 8;

  const shown = useMemo(
    () => sortCandidates(applyFilters(result.candidates, filters, labels), sort),
    [result.candidates, filters, sort, labels],
  );

  function download() {
    const blob = new Blob([toCsv(result, labels)], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = csvFilename(result);
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section aria-labelledby="results-heading" className="flex flex-col gap-4">
      {/* ONE THING LEADS
          This was a heading on the left and three label-and-value pairs plus a
          button on the right, all at the same weight — four items with no order,
          and a reader takes the heading first whatever the layout intends. The
          counts are now a subordinate line under the heading, and the export is
          the only thing competing with it, because it is the only action.

          "Ranked" is gone rather than moved: the status footer reported the same
          number as "Applications", so one screen carried one figure under two
          names, which invites a reader to wonder whether they differ. The count
          belongs here, next to the list; the footer keeps provenance. */}
      <div className="flex flex-wrap items-start justify-between gap-x-8 gap-y-3">
        <div className="min-w-0">
          <h2 id="results-heading" className="text-base font-semibold tracking-tight">
            Shortlist
          </h2>
          <p className="mt-1 text-sm text-muted">
            Ordered best fit first. Ties break by reference, so an identical pair does not reorder
            on re-submission.
          </p>
          <p className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted">
            <span>
              <span className="tabular font-medium text-text">{result.candidates.length}</span>{" "}
              ranked
            </span>
            <span aria-hidden="true">·</span>
            <span>
              posting <span className="tabular font-medium text-text">{result.job_id}</span>
            </span>
            {withGaps > 0 && (
              <>
                <span aria-hidden="true">·</span>
                <span>
                  <span className="tabular font-medium text-text">{withGaps}</span> left something
                  unstated
                </span>
              </>
            )}
          </p>
        </div>
        <Button type="button" size="sm" onClick={download}>
          Export CSV
        </Button>
      </div>

      <Disclaimer text={result.disclaimer} />

      {isLong && (
        <div className="flex flex-col gap-2 rounded-md border border-border bg-surface px-3 py-2.5">
          <div className="flex flex-wrap items-center gap-2">
            <TextInput
              type="search"
              aria-label="Filter the shortlist"
              placeholder="Filter by reference or file name…"
              value={filters.query}
              onChange={(e) => setFilters({ ...filters, query: e.target.value })}
              className="min-w-48 flex-1"
            />
            <Select
              aria-label="Sort the shortlist"
              className="w-auto"
              value={sort}
              onChange={(e) => setSort(e.target.value as SortKey)}
              options={(Object.keys(SORT_LABELS) as SortKey[]).map((key) => ({
                value: key,
                label: SORT_LABELS[key],
              }))}
            />
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Chip
              selected={filters.onlyWithGaps}
              onToggle={() =>
                setFilters({ ...filters, onlyWithGaps: !filters.onlyWithGaps, onlyClean: false })
              }
            >
              CV left gaps
            </Chip>
            <Chip
              selected={filters.onlyClean}
              onToggle={() =>
                setFilters({ ...filters, onlyClean: !filters.onlyClean, onlyWithGaps: false })
              }
            >
              CV stated everything
            </Chip>
            {filtersActive(filters) && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setFilters(NO_FILTERS)}
              >
                Clear
              </Button>
            )}
          </div>

          {/* Stated because it is the trap: narrowing the view does not re-rank,
              and a reviewer reading "1" in a filtered list must know it is the
              real position rather than the best of what is left. */}
          <p className="text-2xs text-muted">
            {filtersActive(filters)
              ? `Showing ${shown.length} of ${result.candidates.length}. Ranks are positions in the full shortlist, not in this view. Export writes all ${result.candidates.length}.`
              : `All ${result.candidates.length} shown. Sorting re-presents the ranking; it never re-ranks.`}
          </p>
        </div>
      )}

      {shown.length === 0 ? (
        <p className="py-6 text-center text-sm text-muted">No candidate matches these filters.</p>
      ) : (
        <div className="overflow-hidden rounded-md border border-border bg-surface">
          {/* A column header, which is the point of moving to a table: the
              caveat on the score is stated once here instead of once per row.
              `aria-hidden` because it is a visual header over a list rather than
              a real table — each row still carries the caveat for a screen
              reader, since a row read on its own has no header above it. */}
          <div
            aria-hidden="true"
            className="flex items-baseline gap-2.5 border-b border-border px-2.5 py-1.5 text-2xs tracking-[0.07em] text-muted uppercase sm:gap-3 sm:px-3"
          >
            <span className="w-5 shrink-0 text-right">#</span>
            <span className="min-w-0 flex-1">Candidate and why</span>
            <span className="shrink-0 normal-case">
              <span className="tracking-[0.07em] uppercase">Score</span>
              <span className="ml-1.5 tracking-normal lowercase">
                this posting only, not a probability
              </span>
            </span>
            <span className="w-5 shrink-0" />
          </div>

          <ol className="divide-y divide-border">
            {shown.map((candidate) => (
              <li key={candidate.candidate_id}>
                <CandidateCard
                  candidate={candidate}
                  displayName={labels.get(candidate.candidate_id)}
                />
              </li>
            ))}
          </ol>
        </div>
      )}
    </section>
  );
}
