import { describe, expect, it } from "vitest";
import { friendlyWarning } from "./warnings";

// Exactly the strings backend/src/guardmatch/parsing/extractor.py emits.
const EMITTED = [
  "years_experience: not stated",
  "employment: no employment section found",
  "employment: section present but no dated roles found",
  "driving_licence: not stated",
  "shift_availability: not stated",
  "certification: unrecognised entry 'chainsaw ticket'",
];

describe("friendlyWarning", () => {
  it("has a phrasing for every warning the parser emits", () => {
    for (const warning of EMITTED) {
      expect(friendlyWarning(warning), warning).not.toBe(warning);
    }
  });

  it("describes the document, never the applicant", () => {
    // "Did not say whether a licence is held" and "has no licence" are
    // different claims, and the parser only ever makes the first.
    const labels = EMITTED.map(friendlyWarning).join(" ").toLowerCase();
    for (const forbidden of ["no driving licence", "lacks", "unqualified", "has none"]) {
      expect(labels).not.toContain(forbidden);
    }
  });

  it("distinguishes a missing employment section from one with no dated roles", () => {
    // The features differ: a missing section leaves site_type_match null,
    // while a present-but-undated one is a different parse outcome.
    expect(friendlyWarning("employment: no employment section found")).not.toBe(
      friendlyWarning("employment: section present but no dated roles found"),
    );
  });

  it("falls back to the raw string rather than hiding an unknown warning", () => {
    expect(friendlyWarning("something_new: not stated")).toBe("something_new: not stated");
  });
});
