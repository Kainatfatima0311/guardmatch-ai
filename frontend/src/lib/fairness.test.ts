import { describe, expect, it } from "vitest";
import {
  auditVerdict,
  belowThreshold,
  formatRate,
  formatRatio,
  groupsByRate,
  overallVerdict,
  ratioPosition,
} from "./fairness";
import type { AttributeAudit, FairnessResponse, GroupOutcome } from "./types";

const group = (name: string, rate: number): GroupOutcome => ({
  group: name,
  n_appearances: 1000,
  n_in_top_k: Math.round(rate * 1000),
  n_qualified: 300,
  n_qualified_in_top_k: 120,
  selection_rate: rate,
  qualified_selection_rate: 0.4,
  mean_exposure: 0.24,
});

const audit = (over: Partial<AttributeAudit> = {}): AttributeAudit => ({
  attribute: "gender",
  top_k: 10,
  groups: [group("female", 0.168), group("male", 0.174)],
  suppressed_groups: [],
  adverse_impact_ratio: 0.9649,
  demographic_parity_gap: 0.0059,
  equal_opportunity_gap: 0.0389,
  exposure_ratio: 0.9825,
  selection_p_value: 0.6652,
  qualified_p_value: 0.2067,
  significance_threshold: 0.05,
  n_comparisons: 1,
  passes: true,
  failures: [],
  inconclusive: [],
  ...over,
});

const report = (over: Partial<FairnessResponse> = {}): FairnessResponse => ({
  model_version: "v0.1.0",
  top_k: 10,
  adverse_impact_threshold: 0.8,
  max_gap: 0.1,
  min_group_size: 30,
  n_postings: 50,
  n_rows: 3041,
  passes: true,
  failures: [],
  inconclusive: [],
  attributes: [audit()],
  ...over,
});

describe("auditVerdict", () => {
  it("returns pass only when nothing else was reported", () => {
    expect(auditVerdict(audit())).toBe("pass");
  });

  it("returns inconclusive for a ratio below threshold that still passes", () => {
    // This is the released `age_band` case and the reason this function exists:
    // 0.627 against a 0.80 threshold, with `passes: true`, because the gap is not
    // distinguishable from noise after correcting for 10 comparisons. Reading
    // `passes` alone would draw a green tick over "cannot tell".
    const unclear = audit({
      attribute: "age_band",
      adverse_impact_ratio: 0.6275,
      passes: true,
      inconclusive: ["below 0.80 but not distinguishable from noise"],
      n_comparisons: 10,
      significance_threshold: 0.005,
    });

    expect(unclear.passes).toBe(true);
    expect(auditVerdict(unclear)).toBe("inconclusive");
  });

  it("lets a failure outrank an inconclusive result", () => {
    expect(
      auditVerdict(audit({ failures: ["breach"], inconclusive: ["also unclear"] })),
    ).toBe("fail");
  });

  it("treats a cleared report that does not pass as a failure", () => {
    // Defensive: `passes: false` with empty failure lists should not read as a pass.
    expect(auditVerdict(audit({ passes: false }))).toBe("fail");
  });
});

describe("overallVerdict", () => {
  it("carries an inconclusive result even when nothing failed", () => {
    // The released run is exactly this shape: no failures, one inconclusive
    // attribute. A summary built from `failures` alone would report it as clean.
    const r = report({ passes: true, failures: [], inconclusive: ["age_band unclear"] });

    expect(r.failures).toEqual([]);
    expect(overallVerdict(r)).toBe("inconclusive");
  });

  it("reports a failure over everything else", () => {
    expect(overallVerdict(report({ failures: ["gender breach"] }))).toBe("fail");
  });

  it("reports pass on a clean run", () => {
    expect(overallVerdict(report())).toBe("pass");
  });
});

describe("belowThreshold", () => {
  it("is independent of the verdict", () => {
    // A reviewer must be able to see that the number is low *and* that the audit
    // draws no conclusion from it. Collapsing the two is how "cannot tell" gets
    // read as "fine".
    const unclear = audit({ adverse_impact_ratio: 0.6275, inconclusive: ["unclear"] });

    expect(belowThreshold(unclear, 0.8)).toBe(true);
    expect(auditVerdict(unclear)).toBe("inconclusive");
  });

  it("is false at or above the line", () => {
    expect(belowThreshold(audit({ adverse_impact_ratio: 0.8 }), 0.8)).toBe(false);
  });
});

describe("ratioPosition", () => {
  it("clamps a ratio above one, which happens when the groups invert", () => {
    expect(ratioPosition(1.4)).toBe(1);
    expect(ratioPosition(-0.2)).toBe(0);
    expect(ratioPosition(0.627)).toBeCloseTo(0.627);
  });
});

describe("formatting", () => {
  it("keeps four decimals on ratios, matching the audit elsewhere", () => {
    expect(formatRatio(0.6275)).toBe("0.6275");
    expect(formatRatio(1)).toBe("1.0000");
  });

  it("renders selection rates as percentages", () => {
    expect(formatRate(0.16784)).toBe("16.8%");
  });
});

describe("groupsByRate", () => {
  it("leads with the lowest group, which the ratio is computed from", () => {
    const sorted = groupsByRate(
      audit({ groups: [group("high", 0.3), group("low", 0.1), group("mid", 0.2)] }),
    );

    expect(sorted.map((g) => g.group)).toEqual(["low", "mid", "high"]);
  });

  it("does not mutate the audit it was given", () => {
    const a = audit({ groups: [group("high", 0.3), group("low", 0.1)] });
    groupsByRate(a);

    expect(a.groups.map((g) => g.group)).toEqual(["high", "low"]);
  });
});
