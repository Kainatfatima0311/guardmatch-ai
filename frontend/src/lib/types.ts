/**
 * The API contract, mirrored by hand.
 *
 * These types are written against `backend/src/guardmatch/schemas/`, not
 * generated from the OpenAPI document. That is a deliberate trade: generated
 * types drift silently when nobody regenerates them, whereas a hand-written
 * mirror that falls out of step produces a type error the moment a response is
 * used. The contract is small enough — three request models and four response
 * models — that hand-writing it costs less than owning a generator.
 *
 * Two properties of the backend contract that the types have to preserve:
 *
 *   1. `null` is meaningful everywhere it appears. It means "the CV never said",
 *      which is a different claim from "no" and from "zero". Rendering it as 0
 *      would assert something the parser deliberately refused to assert.
 *   2. Every request model is `extra="forbid"`. Sending a field that is not
 *      listed here is a hard 422, not a silently ignored extra — which is what
 *      stops a caller attaching a demographic field and assuming it counted.
 */

// ---------------------------------------------------------------------------
// Closed vocabularies — backend/src/guardmatch/schemas/enums.py
// ---------------------------------------------------------------------------

export const CERTIFICATIONS = [
  "security_licence",
  "first_aid",
  "cpr",
  "fire_safety",
  "cctv_operation",
  "conflict_management",
  "dog_handling",
  "close_protection",
  "health_and_safety",
] as const;
export type CertificationCode = (typeof CERTIFICATIONS)[number];

export const SHIFT_TYPES = ["day", "night", "weekend", "rotating"] as const;
export type ShiftType = (typeof SHIFT_TYPES)[number];

export const SITE_TYPES = [
  "retail",
  "corporate",
  "construction",
  "event",
  "residential",
  "industrial",
] as const;
export type SiteType = (typeof SITE_TYPES)[number];

/**
 * Absence of this gates eligibility rather than merely weakening a candidate,
 * and the feature builder treats it that way through `missing_critical_cert`.
 * The form marks it so a reviewer is not left to infer that from the ranking.
 */
export const CRITICAL_CERTIFICATION: CertificationCode = "security_licence";

// ---------------------------------------------------------------------------
// Boundary limits, enforced server-side. Mirrored so the UI can stop a request
// that would only come back as a 422.
// ---------------------------------------------------------------------------

export const MAX_CV_LENGTH = 20_000; // parsing/patterns.py
export const MAX_RANK_BATCH = 500; // core/config.py
export const MAX_YEARS_EXPERIENCE = 40; // schemas/job.py

// ---------------------------------------------------------------------------
// Requests
// ---------------------------------------------------------------------------

export interface Job {
  job_id: string;
  required_certifications: CertificationCode[];
  min_years_experience: number;
  /** Required. The backend has no default, and the form must not invent one. */
  shift_pattern: ShiftType;
  /** Required, same reason. */
  site_type: SiteType;
  driving_required: boolean;
  description?: string;
}

export interface Candidate {
  candidate_id: string;
  /** 1 to MAX_CV_LENGTH characters. Never logged by the backend. */
  cv_text: string;
}

export interface RankRequest {
  job: Job;
  candidates: Candidate[];
}

// ---------------------------------------------------------------------------
// Responses
// ---------------------------------------------------------------------------

export interface FeatureContribution {
  feature: string;
  /** null when the feature could not be computed — "not stated", never 0. */
  value: number | null;
  /** Signed contribution to the raw ranking score. */
  contribution: number;
}

export interface Explanation {
  base_value: number;
  /** All 12 features, every time, ordered by absolute effect. Never truncated. */
  contributions: FeatureContribution[];
  /** 0 to 5 sentences. This one *is* a selection. */
  reasons: string[];
}

export interface ScoredCandidate {
  candidate_id: string;
  /** 1 is the strongest fit for this posting. */
  rank: number;
  relative_ranking_score: number;
  score_type: "relative_ranking_score";
  explanation: Explanation;
  parse_warnings: string[];
}

export interface RankResponse {
  job_id: string;
  candidates: ScoredCandidate[];
  score_type: "relative_ranking_score";
  model_version: string;
  request_id: string;
  /**
   * Shipped with the data on purpose, so the constraint travels with the result
   * rather than living only in documentation. Render this string; never a copy
   * of it held in the client, which would be free to drift.
   */
  disclaimer: string;
}

export interface ReadyResponse {
  ready: boolean;
  model_version: string;
  /** Why it is not ready. null when it is. */
  detail: string | null;
}

export interface ModelInfoResponse {
  model_version: string;
  trained_at: string;
  data_version: string;
  git_sha: string;
  feature_names: string[];
  metrics: Record<string, number>;
}
