import { describe, expect, it } from "vitest";
import {
  FEATURES,
  FEATURE_ORDER,
  checkAdditivity,
  formatContribution,
  formatFeatureValue,
} from "./features";

describe("feature metadata", () => {
  it("labels every feature the model returns", () => {
    // Responses always carry all 12, so a missing label is a visible gap.
    expect(FEATURE_ORDER).toHaveLength(12);
    for (const name of FEATURE_ORDER) {
      expect(FEATURES[name], `no metadata for ${name}`).toBeDefined();
    }
  });

  it("marks the four monitored proxy features", () => {
    const proxies = FEATURE_ORDER.filter((n) => FEATURES[n]?.proxy);
    expect(proxies).toEqual(["exp_gap", "shift_match", "role_count", "recency_months"]);
  });
});

describe("formatFeatureValue", () => {
  it('renders null as "not stated", never as zero', () => {
    // The parser distinguishes "the CV did not say" from "the answer is no".
    // Collapsing them would assert something it deliberately refused to.
    expect(formatFeatureValue(null)).toBe("not stated");
    expect(formatFeatureValue(0)).toBe("0");
  });

  it("keeps integers integral and rounds the rest", () => {
    expect(formatFeatureValue(2)).toBe("2");
    expect(formatFeatureValue(1.5)).toBe("1.50");
  });
});

describe("formatContribution", () => {
  it("always carries an explicit sign, so direction never depends on colour", () => {
    expect(formatContribution(0.9412)).toBe("+0.9412");
    expect(formatContribution(-0.2107)).toBe("−0.2107");
    expect(formatContribution(0)).toBe("±0.0000");
  });
});

describe("checkAdditivity", () => {
  const contributions = [{ contribution: 0.9412 }, { contribution: 0.5511 }, { contribution: -0.2107 }];

  it("confirms that base value plus contributions reconstructs the score", () => {
    const base = -2.0226;
    const score = base + 0.9412 + 0.5511 - 0.2107;
    expect(checkAdditivity(base, contributions, score).holds).toBe(true);
  });

  it("fails when the parts do not add up to the whole", () => {
    // An explanation that does not reconstruct the score it explains is a story
    // printed beside a number, and the interface must not present it as one.
    expect(checkAdditivity(-2.0226, contributions, 99).holds).toBe(false);
  });

  it("tolerates the rounding that JSON serialisation introduces", () => {
    const base = -2.0226;
    const exact = base + 0.9412 + 0.5511 - 0.2107;
    expect(checkAdditivity(base, contributions, exact + 5e-5).holds).toBe(true);
  });
});
