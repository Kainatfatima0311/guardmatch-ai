import type { CandidateDraft } from "./files";
import type { RankResponse, ScoredCandidate } from "./types";

/**
 * Working through a shortlist, and exporting it.
 *
 * Two rules run through everything here.
 *
 * **Filtering changes the view, never the ranking.** The service ranked the whole
 * batch; hiding rows does not re-rank what is left, and a reviewer who filters to
 * twelve of two hundred and fifty is still looking at positions from the full set.
 * Ranks are never renumbered, so row three of a filtered list still says its real
 * rank.
 *
 * **Sorting must not imply comparability the score does not have.** A LambdaRank
 * output is an ordering within one posting, so sorting by score is only ever a
 * re-presentation of the rank the service already assigned — which is why there is
 * no "sort across postings" and no option that would suggest one.
 */

export type SortKey = "rank" | "score-desc" | "score-asc" | "gaps";

export interface ShortlistFilters {
  /** Matches reference or display name. */
  query: string;
  /** Only candidates whose CV left something unstated. */
  onlyWithGaps: boolean;
  /** Only candidates the model found no reason to count against. */
  onlyClean: boolean;
}

export const NO_FILTERS: ShortlistFilters = {
  query: "",
  onlyWithGaps: false,
  onlyClean: false,
};

export function filtersActive(filters: ShortlistFilters): boolean {
  return Boolean(filters.query.trim()) || filters.onlyWithGaps || filters.onlyClean;
}

/**
 * Apply the view filters.
 *
 * @param names Reference to display name, so a reviewer can search by file name
 *   without the name ever having been sent to the service.
 */
export function applyFilters(
  candidates: ScoredCandidate[],
  filters: ShortlistFilters,
  names: Map<string, string> = new Map(),
): ScoredCandidate[] {
  const query = filters.query.trim().toLowerCase();

  return candidates.filter((candidate) => {
    if (filters.onlyWithGaps && candidate.parse_warnings.length === 0) return false;
    if (filters.onlyClean && candidate.parse_warnings.length > 0) return false;

    if (!query) return true;
    const label = names.get(candidate.candidate_id) ?? "";
    return (
      candidate.candidate_id.toLowerCase().includes(query) ||
      label.toLowerCase().includes(query)
    );
  });
}

/**
 * Sort a view of the shortlist.
 *
 * `rank` is the service's own order and the default. The score sorts are the same
 * information read from either end — they exist because a reviewer scanning for
 * the weakest candidates should not have to scroll to the bottom of two hundred.
 */
export function sortCandidates(candidates: ScoredCandidate[], key: SortKey): ScoredCandidate[] {
  const rows = [...candidates];

  switch (key) {
    case "rank":
      return rows.sort((a, b) => a.rank - b.rank);
    case "score-desc":
      return rows.sort((a, b) => b.relative_ranking_score - a.relative_ranking_score);
    case "score-asc":
      return rows.sort((a, b) => a.relative_ranking_score - b.relative_ranking_score);
    case "gaps":
      // Most gaps first, then by rank, so the tie-break stays deterministic
      // rather than depending on the order the filter happened to produce.
      return rows.sort(
        (a, b) => b.parse_warnings.length - a.parse_warnings.length || a.rank - b.rank,
      );
  }
}

export const SORT_LABELS: Record<SortKey, string> = {
  rank: "Rank",
  "score-desc": "Score, highest first",
  "score-asc": "Score, lowest first",
  gaps: "Most gaps in the CV",
};

/** Reference to display name, for search and export. Browser-side only. */
export function displayNames(drafts: CandidateDraft[]): Map<string, string> {
  const names = new Map<string, string>();
  for (const draft of drafts) {
    if (draft.displayName) names.set(draft.candidate_id.trim(), draft.displayName);
  }
  return names;
}

/** Quote a CSV field. Doubling an embedded quote is the escape CSV defines. */
function csvField(value: string | number): string {
  const text = String(value);
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

/**
 * The shortlist as CSV, with the disclaimer as its first row.
 *
 * The disclaimer leads the file for the same reason the service ships it in every
 * response: **a constraint that travels with the data cannot be left behind.** A
 * CSV is precisely where a ranking stops being a screen a reviewer read carefully
 * and becomes a column someone else sorts — so the sentence saying it is not a
 * hiring decision has to be in the file, not only in the browser it came from.
 *
 * Exports the **whole** shortlist, not the filtered view. Filtering is a way of
 * reading; a file named "shortlist" that silently held a fifth of it would be a
 * different document wearing the same name.
 */
export function toCsv(result: RankResponse, names: Map<string, string> = new Map()): string {
  const lines: string[] = [];

  lines.push(csvField(`DISCLAIMER: ${result.disclaimer}`));
  lines.push(
    csvField(
      `Posting ${result.job_id} · model ${result.model_version} · request ${result.request_id}. ` +
        `Scores are relative to this posting only and are not comparable with any other.`,
    ),
  );
  lines.push("");

  lines.push(
    ["rank", "reference", "name", "score", "score_type", "cv_gaps", "reasons"]
      .map(csvField)
      .join(","),
  );

  for (const candidate of [...result.candidates].sort((a, b) => a.rank - b.rank)) {
    lines.push(
      [
        candidate.rank,
        candidate.candidate_id,
        names.get(candidate.candidate_id) ?? "",
        candidate.relative_ranking_score.toFixed(4),
        candidate.score_type,
        candidate.parse_warnings.length,
        candidate.explanation.reasons.join(" | "),
      ]
        .map(csvField)
        .join(","),
    );
  }

  return lines.join("\r\n") + "\r\n";
}

/** A filename carrying the posting and the model, so two exports never collide. */
export function csvFilename(result: RankResponse): string {
  const safe = result.job_id.replace(/[^a-zA-Z0-9._-]+/g, "_");
  return `shortlist-${safe}-${result.model_version}.csv`;
}
