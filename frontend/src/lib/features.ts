/**
 * Display names for the 12 model features.
 *
 * Every response carries all 12, so all 12 need a label a reviewer can read.
 * The wording is taken from `backend/src/guardmatch/features/builder.py`, and
 * two things are stated deliberately:
 *
 *   - `nullable` records whether the feature can legitimately come back as
 *     `null`. That is not cosmetic: `null` means the CV never stated the fact,
 *     which the model treats differently from a stated zero, and the UI has to
 *     render it as "not stated" rather than as 0.
 *   - `proxy` marks the four features the project's own blocklist registers as
 *     able to carry demographic information indirectly. `shift_match` is the
 *     known worst case and is also the model's single largest input. Surfacing
 *     that in the interface rather than only in the fairness report means a
 *     reviewer sees it at the moment it is acting on a candidate.
 */

export interface FeatureMeta {
  label: string;
  meaning: string;
  nullable: boolean;
  proxy?: string;
}

/** Canonical order, matching backend/src/guardmatch/features/registry.py. */
export const FEATURE_ORDER = [
  "exp_gap",
  "exp_ratio",
  "licence_match",
  "cert_overlap_ratio",
  "cert_overlap_count",
  "missing_critical_cert",
  "shift_match",
  "site_type_match",
  "driving_required_match",
  "extra_cert_count",
  "role_count",
  "recency_months",
] as const;

export const FEATURES: Record<string, FeatureMeta> = {
  exp_gap: {
    label: "Experience gap",
    meaning: "Years above or below the minimum this posting asks for.",
    nullable: true,
    proxy: "Can track age when a long career is read as seniority.",
  },
  exp_ratio: {
    label: "Experience ratio",
    meaning: "Experience as a multiple of the stated minimum, capped at 5×.",
    nullable: true,
  },
  licence_match: {
    label: "Security licence",
    meaning: "Holds the required licence — or the posting does not require one.",
    nullable: false,
  },
  cert_overlap_ratio: {
    label: "Certification coverage",
    meaning: "Share of the required certifications the candidate holds.",
    nullable: false,
  },
  cert_overlap_count: {
    label: "Certifications matched",
    meaning: "How many of the required certifications are held.",
    nullable: false,
  },
  missing_critical_cert: {
    label: "Missing critical certification",
    meaning: "A certification that gates eligibility is absent.",
    nullable: false,
  },
  shift_match: {
    label: "Shift availability",
    meaning: "Available for the shift pattern this role runs.",
    nullable: true,
    proxy: "Availability for night work correlates with caring responsibilities.",
  },
  site_type_match: {
    label: "Site type experience",
    meaning: "Has worked this type of site before.",
    nullable: true,
  },
  driving_required_match: {
    label: "Driving requirement",
    meaning: "Holds a driving licence where the role needs one.",
    nullable: true,
  },
  extra_cert_count: {
    label: "Additional certifications",
    meaning: "Certifications held beyond those the posting asks for.",
    nullable: false,
  },
  role_count: {
    label: "Previous roles",
    meaning: "Prior security roles found in the CV, capped at 6.",
    nullable: true,
    proxy: "A count of roles can stand in for age.",
  },
  recency_months: {
    label: "Time since last role",
    meaning: "Months since the most recent role ended, capped at 240.",
    nullable: true,
    proxy: "Career breaks correlate with caring responsibilities.",
  },
};

export function featureLabel(name: string): string {
  return FEATURES[name]?.label ?? name;
}

/**
 * A feature value for display. `null` becomes "not stated" — never "0", which
 * would assert something the parser deliberately declined to assert.
 */
export function formatFeatureValue(value: number | null): string {
  if (value === null) return "not stated";
  if (Number.isInteger(value)) return String(value);
  return value.toFixed(2);
}

/** Signed, fixed width, so a column of them stays readable. */
export function formatContribution(value: number): string {
  const sign = value > 0 ? "+" : value < 0 ? "−" : "±";
  return `${sign}${Math.abs(value).toFixed(4)}`;
}

/**
 * SHAP here is additive: base value plus every contribution reconstructs the
 * score, to 1e-6, and the backend asserts that before responding. Re-checking
 * it client-side is cheap and turns "trust us" into something the interface can
 * show. The tolerance is loosened to 1e-4 because the wire format is rounded
 * JSON, not the float64s the assertion ran on.
 */
export const ADDITIVITY_TOLERANCE = 1e-4;

export function checkAdditivity(
  baseValue: number,
  contributions: { contribution: number }[],
  score: number,
): { sum: number; delta: number; holds: boolean } {
  const sum = contributions.reduce((acc, c) => acc + c.contribution, baseValue);
  const delta = Math.abs(sum - score);
  return { sum, delta, holds: delta <= ADDITIVITY_TOLERANCE };
}
