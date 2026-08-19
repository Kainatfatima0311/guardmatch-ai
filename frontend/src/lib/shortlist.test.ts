import { describe, expect, it } from "vitest";
import {
  NO_FILTERS,
  applyFilters,
  csvFilename,
  displayNames,
  filtersActive,
  sortCandidates,
  toCsv,
} from "./shortlist";
import type { RankResponse, ScoredCandidate } from "./types";

const candidate = (
  rank: number,
  id: string,
  score: number,
  warnings: string[] = [],
): ScoredCandidate => ({
  candidate_id: id,
  rank,
  relative_ranking_score: score,
  score_type: "relative_ranking_score",
  explanation: {
    base_value: -2,
    contributions: [{ feature: "shift_match", value: 1, contribution: 0.9 }],
    reasons: ["Available for the shift pattern this role needs"],
  },
  parse_warnings: warnings,
});

const SHORTLIST = [
  candidate(1, "okafor", 2.97),
  candidate(2, "bennett", -3.33, ["years_experience: not stated"]),
  candidate(3, "unstated", -3.89, ["years_experience: not stated", "driving_licence: not stated"]),
  candidate(4, "haddad", -4.1),
];

const result: RankResponse = {
  job_id: "j_night",
  candidates: SHORTLIST,
  score_type: "relative_ranking_score",
  model_version: "v0.1.0",
  request_id: "abc123",
  disclaimer:
    "Scores are relative to this job posting only and are not probabilities. This ranking is a shortlisting aid and is not a hiring decision.",
};

describe("applyFilters", () => {
  it("returns everything when nothing is set", () => {
    expect(applyFilters(SHORTLIST, NO_FILTERS)).toHaveLength(4);
  });

  it("never renumbers a rank", () => {
    // The service ranked the whole batch. Hiding rows does not re-rank what is
    // left, so row one of a filtered list must still report its real position —
    // otherwise a reviewer reads "1" as "best of these four".
    const filtered = applyFilters(SHORTLIST, { ...NO_FILTERS, onlyWithGaps: true });

    expect(filtered.map((c) => c.rank)).toEqual([2, 3]);
  });

  it("filters to CVs that left something unstated", () => {
    const filtered = applyFilters(SHORTLIST, { ...NO_FILTERS, onlyWithGaps: true });

    expect(filtered.map((c) => c.candidate_id)).toEqual(["bennett", "unstated"]);
  });

  it("filters to CVs with no gaps", () => {
    const filtered = applyFilters(SHORTLIST, { ...NO_FILTERS, onlyClean: true });

    expect(filtered.map((c) => c.candidate_id)).toEqual(["okafor", "haddad"]);
  });

  it("searches the display name, which never left the browser", () => {
    // The reference is what the service saw; the file name is what the reviewer
    // recognises. Searching has to work on the one they can read.
    const names = new Map([["okafor", "Aisha Okafor CV.pdf"]]);
    const filtered = applyFilters(SHORTLIST, { ...NO_FILTERS, query: "aisha" }, names);

    expect(filtered.map((c) => c.candidate_id)).toEqual(["okafor"]);
  });

  it("searches the reference too", () => {
    expect(
      applyFilters(SHORTLIST, { ...NO_FILTERS, query: "hadd" }).map((c) => c.candidate_id),
    ).toEqual(["haddad"]);
  });

  it("combines a query with a gap filter", () => {
    const filtered = applyFilters(SHORTLIST, {
      query: "un",
      onlyWithGaps: true,
      onlyClean: false,
    });

    expect(filtered.map((c) => c.candidate_id)).toEqual(["unstated"]);
  });
});

describe("filtersActive", () => {
  it("is false for the default and true for anything set", () => {
    expect(filtersActive(NO_FILTERS)).toBe(false);
    expect(filtersActive({ ...NO_FILTERS, query: "  " })).toBe(false);
    expect(filtersActive({ ...NO_FILTERS, query: "a" })).toBe(true);
    expect(filtersActive({ ...NO_FILTERS, onlyWithGaps: true })).toBe(true);
  });
});

describe("sortCandidates", () => {
  it("defaults to the order the service assigned", () => {
    expect(sortCandidates(SHORTLIST, "rank").map((c) => c.rank)).toEqual([1, 2, 3, 4]);
  });

  it("sorts by score in both directions", () => {
    expect(sortCandidates(SHORTLIST, "score-desc").map((c) => c.candidate_id)[0]).toBe("okafor");
    expect(sortCandidates(SHORTLIST, "score-asc").map((c) => c.candidate_id)[0]).toBe("haddad");
  });

  it("sorts by gaps with a deterministic tie-break", () => {
    // Ties broken by rank rather than left to whatever order the filter produced,
    // so the same shortlist always presents the same way.
    const sorted = sortCandidates(SHORTLIST, "gaps");

    expect(sorted.map((c) => c.candidate_id)).toEqual([
      "unstated",
      "bennett",
      "okafor",
      "haddad",
    ]);
  });

  it("does not mutate what it was given", () => {
    const before = SHORTLIST.map((c) => c.candidate_id);
    sortCandidates(SHORTLIST, "score-asc");

    expect(SHORTLIST.map((c) => c.candidate_id)).toEqual(before);
  });
});

describe("toCsv", () => {
  it("leads with the disclaimer", () => {
    // Same argument as the service shipping it in every response: a constraint
    // that travels with the data cannot be left behind. A CSV is exactly where a
    // ranking stops being a screen someone read and becomes a column someone
    // else sorts.
    const csv = toCsv(result);

    expect(csv.split("\r\n")[0]).toContain("DISCLAIMER");
    expect(csv).toContain("is not a hiring decision");
  });

  it("records the posting, model and request id", () => {
    const csv = toCsv(result);

    expect(csv).toContain("j_night");
    expect(csv).toContain("v0.1.0");
    expect(csv).toContain("abc123");
  });

  it("states that scores are not comparable with another posting", () => {
    expect(toCsv(result)).toContain("not comparable");
  });

  it("exports the whole shortlist in rank order", () => {
    const rows = toCsv(result).trim().split("\r\n").slice(4);

    expect(rows).toHaveLength(4);
    expect(rows[0]!.startsWith("1,okafor")).toBe(true);
    expect(rows[3]!.startsWith("4,haddad")).toBe(true);
  });

  it("includes the display name when there is one", () => {
    const csv = toCsv(result, new Map([["okafor", "Aisha Okafor CV.pdf"]]));

    expect(csv).toContain("Aisha Okafor CV.pdf");
  });

  it("escapes a field containing a comma or a quote", () => {
    // Reasons contain prose and are joined with a pipe; a stray comma there would
    // otherwise shift every later column by one.
    const awkward: RankResponse = {
      ...result,
      candidates: [
        {
          ...candidate(1, "x", 1),
          explanation: {
            base_value: -2,
            contributions: [],
            reasons: ['Holds 100% of certifications, including the "critical" one'],
          },
        },
      ],
    };

    const line = toCsv(awkward).trim().split("\r\n").at(-1)!;
    expect(line).toContain('""critical""');
    expect(line.split(",").length).toBeGreaterThan(6);
  });

  it("does not renumber ranks on export", () => {
    const partial: RankResponse = { ...result, candidates: [SHORTLIST[2]!] };
    const line = toCsv(partial).trim().split("\r\n").at(-1)!;

    expect(line.startsWith("3,unstated")).toBe(true);
  });
});

describe("csvFilename", () => {
  it("carries the posting and the model, so two exports never collide", () => {
    expect(csvFilename(result)).toBe("shortlist-j_night-v0.1.0.csv");
  });

  it("strips characters a filesystem would object to", () => {
    expect(csvFilename({ ...result, job_id: "night / site #2" })).toBe(
      "shortlist-night_site_2-v0.1.0.csv",
    );
  });
});

describe("displayNames", () => {
  it("maps references to file names, skipping drafts without one", () => {
    const names = displayNames([
      { candidate_id: " okafor ", cv_text: "x", displayName: "Aisha.pdf" },
      { candidate_id: "typed", cv_text: "x" },
    ]);

    expect(names.get("okafor")).toBe("Aisha.pdf");
    expect(names.has("typed")).toBe(false);
  });
});
