import { describe, expect, it } from "vitest";
import { requirementBadge, requirementsFor, yearsFromGap } from "./requirements";
import type { CertificationCode, Explanation, Job } from "./types";

const JOB: Job = {
  job_id: "j_night",
  required_certifications: ["security_licence", "fire_safety", "cpr"],
  min_years_experience: 2,
  shift_pattern: "night",
  site_type: "industrial",
  driving_required: true,
};

/** Only the values matter here; the contributions themselves are irrelevant. */
function explain(values: Record<string, number | null>): Explanation {
  return {
    base_value: -2,
    reasons: [],
    contributions: Object.entries(values).map(([feature, value]) => ({
      feature,
      value,
      contribution: 0,
    })),
  };
}

const ALL_MET = {
  exp_gap: 1.1,
  licence_match: 1,
  cert_overlap_count: 3,
  shift_match: 1,
  site_type_match: 1,
  driving_required_match: 1,
};

describe("requirementsFor", () => {
  it("counts only what the posting asked for", () => {
    const s = requirementsFor(JOB, explain(ALL_MET));

    // experience, licence, other certifications, shift, site, driving
    expect(s.asked).toBe(6);
    expect(s.met).toBe(6);
    expect(s.unmet).toBe(0);
    expect(s.notStated).toBe(0);
  });

  it("omits experience entirely when no minimum was asked for", () => {
    // Zero is not a requirement that happens to be met. The form says so too:
    // at 0, experience stops being a factor.
    const s = requirementsFor({ ...JOB, min_years_experience: 0 }, explain(ALL_MET));

    expect(s.requirements.map((r) => r.feature)).not.toContain("exp_gap");
    expect(s.asked).toBe(5);
  });

  it("omits driving when the posting does not require it", () => {
    const s = requirementsFor({ ...JOB, driving_required: false }, explain(ALL_MET));

    expect(s.requirements.map((r) => r.feature)).not.toContain("driving_required_match");
    expect(s.asked).toBe(5);
  });

  it("omits certifications when none are asked for", () => {
    const s = requirementsFor({ ...JOB, required_certifications: [] }, explain(ALL_MET));
    const features = s.requirements.map((r) => r.feature);

    expect(features).not.toContain("licence_match");
    expect(features).not.toContain("cert_overlap_count");
    expect(s.asked).toBe(4);
  });

  it("asks for the licence alone without inventing an 'other certifications' row", () => {
    const s = requirementsFor(
      { ...JOB, required_certifications: ["security_licence"] as CertificationCode[] },
      explain({ ...ALL_MET, cert_overlap_count: 1 }),
    );

    expect(s.requirements.map((r) => r.feature)).toContain("licence_match");
    expect(s.requirements.map((r) => r.feature)).not.toContain("cert_overlap_count");
  });
});

describe("a null is never a failure", () => {
  // The most important property in this module. `null` means the parser did not
  // find the fact, not that the candidate lacks it, and the model itself treats
  // those differently — a stated negative is penalised harder than an unknown.
  // Counting an unknown as unmet would report a candidate as failing something
  // their CV merely did not mention.

  it("reports an unstated value as not-stated, not as unmet", () => {
    const s = requirementsFor(JOB, explain({ ...ALL_MET, driving_required_match: null }));

    expect(s.unmet).toBe(0);
    expect(s.notStated).toBe(1);
    expect(s.met).toBe(5);
    expect(s.requirements.find((r) => r.feature === "driving_required_match")!.state).toBe(
      "not-stated",
    );
  });

  it("distinguishes a stated zero from an absent value", () => {
    const absent = requirementsFor(JOB, explain({ ...ALL_MET, shift_match: null }));
    const stated = requirementsFor(JOB, explain({ ...ALL_MET, shift_match: 0 }));

    expect(absent.notStated).toBe(1);
    expect(absent.unmet).toBe(0);
    expect(stated.unmet).toBe(1);
    expect(stated.notStated).toBe(0);
  });

  it("treats a missing feature the same as a null one", () => {
    // A response that simply does not carry the feature must not read as unmet
    // either. Absent and absent-valued are the same claim: nothing is known.
    const withoutDriving = Object.fromEntries(
      Object.entries(ALL_MET).filter(([k]) => k !== "driving_required_match"),
    );
    const s = requirementsFor(JOB, explain(withoutDriving));

    expect(s.notStated).toBe(1);
    expect(s.unmet).toBe(0);
  });

  it("never lets met plus unmet plus not-stated disagree with asked", () => {
    for (const values of [
      ALL_MET,
      { ...ALL_MET, exp_gap: null, licence_match: 0 },
      { ...ALL_MET, shift_match: null, site_type_match: null, cert_overlap_count: null },
      { exp_gap: null, licence_match: null, cert_overlap_count: null },
    ]) {
      const s = requirementsFor(JOB, explain(values));
      expect(s.met + s.unmet + s.notStated).toBe(s.asked);
    }
  });
});

describe("certifications are counted without double-counting the licence", () => {
  it("subtracts the licence, which has its own row", () => {
    // Three required: licence, fire safety, CPR. Two held in total. The licence is
    // one of them, so one of the two others is held — not two.
    const s = requirementsFor(JOB, explain({ ...ALL_MET, cert_overlap_count: 2, licence_match: 1 }));
    const others = s.requirements.find((r) => r.feature === "cert_overlap_count")!;

    expect(others.detail).toBe("1 of 2 held");
    expect(others.state).toBe("unmet");
  });

  it("does not subtract a licence the posting did not ask for", () => {
    const job = { ...JOB, required_certifications: ["fire_safety", "cpr"] as CertificationCode[] };
    const s = requirementsFor(job, explain({ ...ALL_MET, cert_overlap_count: 2, licence_match: 0 }));
    const others = s.requirements.find((r) => r.feature === "cert_overlap_count")!;

    expect(others.detail).toBe("2 of 2 held");
    expect(others.state).toBe("met");
  });

  it("refuses to subtract when either figure is unknown", () => {
    // The arithmetic is only defensible when both values are known. Guessing
    // would produce a count that looks exact and is not.
    const s = requirementsFor(JOB, explain({ ...ALL_MET, licence_match: null }));
    const others = s.requirements.find((r) => r.feature === "cert_overlap_count")!;

    expect(others.state).toBe("not-stated");
    expect(others.detail).toContain("did not say");
  });

  it("never reports a negative count", () => {
    const s = requirementsFor(JOB, explain({ ...ALL_MET, cert_overlap_count: 0, licence_match: 1 }));
    const others = s.requirements.find((r) => r.feature === "cert_overlap_count")!;

    expect(others.detail).toBe("0 of 2 held");
  });
});

describe("yearsFromGap", () => {
  it("reconstructs the years the CV showed", () => {
    expect(yearsFromGap(1.1, 2)).toBe(3.1);
    expect(yearsFromGap(-1, 4)).toBe(3);
  });

  it("works when the posting asked for no minimum, where a ratio would not", () => {
    // exp_ratio is undefined at a zero minimum; the gap is the years themselves.
    expect(yearsFromGap(6, 0)).toBe(6);
  });

  it("stays null when the CV did not say", () => {
    expect(yearsFromGap(null, 2)).toBeNull();
    expect(yearsFromGap(undefined, 2)).toBeNull();
  });
});

describe("requirementBadge", () => {
  it("reads as met out of asked", () => {
    expect(requirementBadge(requirementsFor(JOB, explain(ALL_MET)))).toBe(
      "6 of 6 requirements met",
    );
  });

  it("names the not-stated count, so the remainder cannot be read as failures", () => {
    // Without this, "4 of 6" invites the reader to conclude two failures when one
    // of them is a CV that stayed silent.
    const s = requirementsFor(
      JOB,
      explain({ ...ALL_MET, shift_match: 0, driving_required_match: null }),
    );

    expect(requirementBadge(s)).toBe("4 of 6 requirements met · 1 not stated");
  });

  it("says nothing about not-stated when there is none", () => {
    const s = requirementsFor(JOB, explain({ ...ALL_MET, shift_match: 0 }));

    expect(requirementBadge(s)).not.toContain("not stated");
  });
});
