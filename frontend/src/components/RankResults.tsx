import type { RankResponse } from "@/lib/types";
import CandidateCard from "./CandidateCard";
import Disclaimer from "./Disclaimer";
import { Stat } from "./ui";

/**
 * The shortlist.
 *
 * Order comes from the service and is not re-sorted here. Ties are already broken
 * deterministically by candidate id server-side, so two identical applications
 * keep a stable order instead of drifting with upload position — re-sorting in the
 * client would throw that away.
 *
 * The disclaimer sits above the list rather than below it. Below, it is a
 * footnote to a decision already formed; above, it is a condition on reading what
 * follows.
 */
export default function RankResults({ result }: { result: RankResponse }) {
  const withGaps = result.candidates.filter((c) => c.parse_warnings.length > 0).length;

  return (
    <section aria-labelledby="results-heading" className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-x-8 gap-y-3">
        <div>
          <h2 id="results-heading" className="text-xl font-semibold tracking-tight">
            Shortlist
          </h2>
          <p className="mt-0.5 text-sm text-muted">
            Ordered best fit first. Ties break by reference, so an identical pair does not reorder
            on re-submission.
          </p>
        </div>
        {/* A div rather than a dl: `Stat` renders labelled spans, not dt/dd
            pairs, and a dl whose children are not definition items is worse
            markup than a div that never claimed to be one. */}
        <div className="flex flex-wrap gap-x-7 gap-y-2">
          <Stat label="Ranked" value={String(result.candidates.length)} mono />
          <Stat label="Posting" value={result.job_id} mono />
          {withGaps > 0 && <Stat label="CVs with gaps" value={String(withGaps)} mono />}
        </div>
      </div>

      <Disclaimer text={result.disclaimer} />

      <ol className="flex flex-col gap-3">
        {result.candidates.map((candidate) => (
          <li key={candidate.candidate_id}>
            <CandidateCard candidate={candidate} />
          </li>
        ))}
      </ol>
    </section>
  );
}
