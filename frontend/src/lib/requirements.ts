import { CRITICAL_CERTIFICATION, type Explanation, type Job } from "./types";

/**
 * What a posting asked for, and what one candidate's CV showed against it.
 *
 * THIS FILE EXISTS BECAUSE OF WHAT IT REPLACED
 *
 * The supplied mockup put a coloured badge on every candidate reading "Strong
 * match", "Moderate match" or "Weak match", above a score out of 100. Neither is
 * available. The model emits a relative ranking score within a single posting; it
 * is not calibrated to a 0-100 scale and it is not calibrated to the graded
 * labels it trained on, so any level shown would be a threshold the interface
 * invented. The model card's second condition is explicit that nothing in the
 * output supports one.
 *
 * What *is* available is a count of the posting's own stated requirements against
 * feature values the model actually used. "5 of 6 requirements met" is something a
 * reviewer can check against the CV themselves. "Strong match" is a judgement
 * nothing here made.
 *
 * A NULL IS NOT A FAILURE
 *
 * The single most important rule in this file. A feature value of `null` means the
 * parser did not find the fact, not that the candidate lacks it — and the model
 * treats those differently, penalising a stated negative harder than an unknown.
 * Counting an unknown as unmet would report a candidate as failing a requirement
 * their CV simply did not mention, which is the same silent misreading the whole
 * project is built to avoid. So `notStated` is its own state, it is never folded
 * into `unmet`, and the total is reported with it named.
 *
 * ONLY WHAT THE POSTING ASKED
 *
 * A requirement the posting did not state is not a requirement. If experience is
 * left at zero, or driving is not required, or no certifications are listed, those
 * do not appear at all — they are not requirements that happen to be met.
 */

export type RequirementState = "met" | "unmet" | "not-stated";

export interface Requirement {
  /** The feature this was derived from, so a reader can find it in the table. */
  feature: string;
  label: string;
  state: RequirementState;
  /** The figures behind the state, where there are any. */
  detail?: string;
}

export interface RequirementSummary {
  requirements: Requirement[];
  /** Requirements the posting stated. `met + unmet + notStated`. */
  asked: number;
  met: number;
  unmet: number;
  notStated: number;
}

/** `null` stays `null`; anything else becomes met or unmet on a 1/0 flag. */
function fromFlag(value: number | null | undefined): RequirementState {
  if (value === null || value === undefined) return "not-stated";
  return value >= 1 ? "met" : "unmet";
}

function valuesOf(explanation: Explanation): Map<string, number | null> {
  return new Map(explanation.contributions.map((c) => [c.feature, c.value]));
}

/**
 * Years of experience the CV showed, reconstructed from the gap.
 *
 * `exp_gap` is `years - min_years_experience`, so adding the minimum back gives
 * the years. Derived from the gap rather than from `exp_ratio` because a ratio is
 * undefined when the minimum is zero, and a posting may legitimately ask for no
 * minimum at all.
 */
export function yearsFromGap(gap: number | null | undefined, minYears: number): number | null {
  if (gap === null || gap === undefined) return null;
  return Math.round((gap + minYears) * 10) / 10;
}

export function requirementsFor(job: Job, explanation: Explanation): RequirementSummary {
  const v = valuesOf(explanation);
  const requirements: Requirement[] = [];

  // --- experience, only when a minimum was asked for --------------------
  if (job.min_years_experience > 0) {
    const gap = v.get("exp_gap");
    const years = yearsFromGap(gap, job.min_years_experience);
    requirements.push({
      feature: "exp_gap",
      label: "Minimum experience",
      state: gap === null || gap === undefined ? "not-stated" : gap >= 0 ? "met" : "unmet",
      detail:
        years === null
          ? `${job.min_years_experience} years needed; the CV did not say`
          : `${years} years, ${job.min_years_experience} needed`,
    });
  }

  // --- the gating certification, on its own because it is scored on its own
  const licenceRequired = job.required_certifications.includes(CRITICAL_CERTIFICATION);
  if (licenceRequired) {
    const licence = v.get("licence_match");
    requirements.push({
      feature: "licence_match",
      label: "Security licence",
      state: fromFlag(licence),
      detail: "Gates eligibility; its absence is scored separately",
    });
  }

  // --- the remaining certifications, counted -----------------------------
  const otherAsked = job.required_certifications.filter((c) => c !== CRITICAL_CERTIFICATION).length;
  if (otherAsked > 0) {
    const total = v.get("cert_overlap_count");
    const licence = v.get("licence_match");
    // The count includes the licence, which already has its own row above, so it
    // is subtracted out rather than counted twice. If either figure is unknown the
    // subtraction is not defensible, and the requirement reads not stated.
    const held =
      total === null || total === undefined || licence === null || licence === undefined
        ? null
        : Math.max(0, total - (licenceRequired ? licence : 0));
    requirements.push({
      feature: "cert_overlap_count",
      label: otherAsked === 1 ? "Other required certification" : "Other required certifications",
      state: held === null ? "not-stated" : held >= otherAsked ? "met" : "unmet",
      detail:
        held === null
          ? `${otherAsked} asked for; the CV did not say`
          : `${held} of ${otherAsked} held`,
    });
  }

  // --- availability and site, which a posting always states --------------
  requirements.push({
    feature: "shift_match",
    label: "Shift availability",
    state: fromFlag(v.get("shift_match")),
    detail: `${job.shift_pattern} shift`,
  });

  requirements.push({
    feature: "site_type_match",
    label: "Site experience",
    state: fromFlag(v.get("site_type_match")),
    detail: `${job.site_type.replace(/_/g, " ")} site`,
  });

  // --- driving, only when required ---------------------------------------
  if (job.driving_required) {
    requirements.push({
      feature: "driving_required_match",
      label: "Driving licence",
      state: fromFlag(v.get("driving_required_match")),
    });
  }

  const met = requirements.filter((r) => r.state === "met").length;
  const unmet = requirements.filter((r) => r.state === "unmet").length;
  const notStated = requirements.filter((r) => r.state === "not-stated").length;

  return { requirements, asked: requirements.length, met, unmet, notStated };
}

/**
 * The badge text.
 *
 * The not-stated count is appended whenever there is one, so `met` and `asked`
 * can never be read as "met" and "failed". Without it, "4 of 6" invites the
 * reader to conclude two failures when one of them is a CV that stayed silent.
 */
export function requirementBadge(summary: RequirementSummary): string {
  const base = `${summary.met} of ${summary.asked} requirements met`;
  return summary.notStated > 0 ? `${base} · ${summary.notStated} not stated` : base;
}
