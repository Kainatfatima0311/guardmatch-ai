/**
 * Turning the parser's warning strings into something a reviewer can read.
 *
 * Kept out of the component so it can be tested. Every phrasing describes
 * something the *document* did not say, never something the applicant lacks.
 * That is not politeness: the parser records an unstated fact as `null` and
 * deliberately refuses to infer "no" from silence, so a label reading "no
 * driving licence" for a CV that never mentioned driving would reintroduce
 * exactly the inference the pipeline declined to make.
 *
 * Source of the strings: backend/src/guardmatch/parsing/extractor.py
 */

interface Phrasing {
  prefix: string;
  label: string;
}

const PHRASINGS: Phrasing[] = [
  { prefix: "years_experience: not stated", label: "Did not state years of experience" },
  { prefix: "employment: no employment section found", label: "No employment history section" },
  {
    prefix: "employment: section present but no dated roles found",
    label: "Employment section present, but no dated roles in it",
  },
  {
    prefix: "driving_licence: not stated",
    label: "Did not say whether a driving licence is held",
  },
  { prefix: "shift_availability: not stated", label: "Did not state shift availability" },
  {
    prefix: "certification:",
    label: "An entry in the certifications list was not recognised",
  },
];

/** Falls back to the raw string, so a warning added backend-side still shows. */
export function friendlyWarning(warning: string): string {
  return PHRASINGS.find((p) => warning.startsWith(p.prefix))?.label ?? warning;
}
