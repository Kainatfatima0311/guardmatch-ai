import type { Candidate } from "./types";

/**
 * Sample applications, for trying the workspace without pasting real CVs.
 *
 * Three are written in the shapes the parser handles well — recognised section
 * headings, bulleted certifications, dated roles with a site after the dash.
 *
 * The fourth is deliberately thin, and it is the important one. It produces
 * seven `null` feature values and four parse warnings, which is the only way to
 * see the difference between "the CV did not say" and "the answer is no". A
 * demo built only from well-formed CVs would show an interface that never has
 * to admit it does not know something.
 */
export const SAMPLE_CANDIDATES: Candidate[] = [
  {
    candidate_id: "c_okafor",
    cv_text: `PROFILE
Reliable security officer with 6 years of experience on construction and industrial sites.

CERTIFICATIONS
- SIA licence
- fire marshal
- first aid at work

AVAILABILITY
Available for night shifts and rotating shifts.

EMPLOYMENT
Site Security Officer, Meridian Facilities (2024 - present) - construction site
Security Officer, Harbour Industrial Services (2021 - 2024) - industrial site

ADDITIONAL
Full clean driving licence.`,
  },
  {
    candidate_id: "c_bennett",
    cv_text: `PROFILE
Retail security specialist with 8 years of experience in high-footfall stores.

CERTIFICATIONS
- SIA badge
- conflict management
- CCTV operation
- emergency first aid

AVAILABILITY
Available for day shifts and weekend shifts.

EMPLOYMENT
Loss Prevention Officer, Northgate Retail Group (2019 - present) - retail site
Store Security Assistant, Colwyn Stores (2018 - 2019) - retail site

ADDITIONAL
No driving licence.`,
  },
  {
    candidate_id: "c_haddad",
    cv_text: `PROFILE
Corporate security officer, 3 years of experience across office and event work.

CERTIFICATIONS
- close protection
- health and safety
- CPR

AVAILABILITY
Available for night shifts.

EMPLOYMENT
Front of House Security, Ashcroft Corporate Services (2023 - present) - corporate site

ADDITIONAL
Full driving licence held.`,
  },
  {
    candidate_id: "c_unstated",
    cv_text: `PROFILE
Seeking a security position. Hard working and punctual.

CERTIFICATIONS
- fire marshal`,
  },
];

/** A posting the samples are written against, so the demo shows a real spread. */
export const SAMPLE_JOB = {
  job_id: "j_nightsite",
  required_certifications: ["security_licence", "fire_safety"] as const,
  min_years_experience: 4,
  shift_pattern: "night" as const,
  site_type: "construction" as const,
  driving_required: true,
};
