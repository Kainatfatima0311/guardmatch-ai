import type { RankResponse } from "@/lib/types";
import CandidateCard from "./CandidateCard";
import Disclaimer from "./Disclaimer";

/**
 * The shortlist.
 *
 * Order comes from the backend and is not re-sorted here. Ties are already
 * broken deterministically by candidate id server-side, so two identical
 * applications keep a stable order instead of drifting with upload position —
 * re-sorting in the client would throw that away.
 */
export default function RankResults({ result }: { result: RankResponse }) {
  return (
    <section aria-labelledby="results-heading" className="flex flex-col gap-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="results-heading" className="text-lg font-semibold tracking-tight">
          Shortlist
        </h2>
        <p className="text-sm text-muted">
          {result.candidates.length} ranked for {result.job_id}
        </p>
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
