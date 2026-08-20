"use client";

import {
  CERTIFICATIONS,
  CRITICAL_CERTIFICATION,
  MAX_YEARS_EXPERIENCE,
  SHIFT_TYPES,
  SITE_TYPES,
  type CertificationCode,
  type Job,
  type ShiftType,
  type SiteType,
} from "@/lib/types";
import { Card, CardBody, CardHeader, Chip, Field, Select, TextInput, Toggle } from "./ui";

/**
 * The posting being ranked against.
 *
 * Every control is driven by the closed vocabularies in
 * `backend/src/guardmatch/schemas/enums.py`, so the form cannot offer a value the
 * API would reject — the request models are `extra="forbid"` and the enums are
 * exhaustive, which makes an unrecognised value a 422 rather than a near-miss the
 * backend quietly tolerates.
 *
 * `shift_pattern` and `site_type` have no default here because they have none on
 * the backend either. Pre-selecting "day" and "retail" would mean every reviewer
 * who did not look at those two fields silently ranked against a posting the
 * system invented for them — and `shift_match` is the model's largest input, so
 * an unnoticed default moves results more than most fields a reviewer does fill
 * in.
 */

const LABELS: Record<string, string> = {
  security_licence: "Security licence",
  first_aid: "First aid",
  cpr: "CPR",
  fire_safety: "Fire safety",
  cctv_operation: "CCTV operation",
  conflict_management: "Conflict management",
  dog_handling: "Dog handling",
  close_protection: "Close protection",
  health_and_safety: "Health and safety",
  day: "Day",
  night: "Night",
  weekend: "Weekend",
  rotating: "Rotating",
  retail: "Retail",
  corporate: "Corporate",
  construction: "Construction",
  event: "Event",
  residential: "Residential",
  industrial: "Industrial",
};

const label = (v: string) => LABELS[v] ?? v;
const options = (values: readonly string[]) => values.map((v) => ({ value: v, label: label(v) }));

/** The form's own shape. `""` is "not yet chosen", which is a real state in a
 *  form and not a real state in the API contract. Keeping them separate is what
 *  stops an unfilled select being submitted as though it were an answer. */
export type JobDraft = Omit<Job, "shift_pattern" | "site_type"> & {
  shift_pattern: ShiftType | "";
  site_type: SiteType | "";
};

export interface JobFormErrors {
  shift_pattern?: string;
  site_type?: string;
  job_id?: string;
}

export default function JobForm({
  value,
  errors,
  onChange,
  disabled,
}: {
  value: JobDraft;
  errors?: JobFormErrors;
  onChange: (next: JobDraft) => void;
  disabled?: boolean;
}) {
  const set = <K extends keyof JobDraft>(key: K, v: JobDraft[K]) =>
    onChange({ ...value, [key]: v });

  const toggleCert = (code: CertificationCode) => {
    const held = value.required_certifications;
    set(
      "required_certifications",
      held.includes(code) ? held.filter((c) => c !== code) : [...held, code],
    );
  };

  const chosen = value.required_certifications.length;

  return (
    /* THE CONTAINER QUERY IS RETIRED, AND THE REASON IS WORTH KEEPING
       These fields used to go two-across, keyed to `sm:` — a *viewport*
       breakpoint, while this panel's width comes from the grid column it sits in.
       Those are different questions that had been agreeing by luck, and a
       two-column page layout at `md` broke the agreement at once. The fix was a
       container query, and it was right.
       It is gone now because the layout it existed for is gone: a definition list
       is one column at every width, so there is nothing to switch. The note stays
       so that whoever reintroduces a multi-column grid here reaches for
       `@container` rather than for `sm:`. */
    <Card>
      <CardHeader step={1} title="Posting" subtitle="What this vacancy actually needs." />
      <CardBody className="flex flex-col gap-4">
        <div className="flex flex-col gap-2.5">
          <Field label="Shift" inline error={errors?.shift_pattern}>
            {(p) => (
              <Select
                {...p}
                options={options(SHIFT_TYPES)}
                placeholder="Choose a shift"
                invalid={Boolean(errors?.shift_pattern)}
                value={value.shift_pattern}
                disabled={disabled}
                onChange={(e) => set("shift_pattern", e.target.value as ShiftType)}
              />
            )}
          </Field>

          <Field label="Site" inline error={errors?.site_type}>
            {(p) => (
              <Select
                {...p}
                options={options(SITE_TYPES)}
                placeholder="Choose a site type"
                invalid={Boolean(errors?.site_type)}
                value={value.site_type}
                disabled={disabled}
                onChange={(e) => set("site_type", e.target.value as SiteType)}
              />
            )}
          </Field>

          <Field
            label="Min years"
            inline
            hint={`0 to ${MAX_YEARS_EXPERIENCE}. A candidate below it is not excluded — the gap becomes one factor among twelve.`}
          >
            {(p) => (
              <TextInput
                {...p}
                type="number"
                min={0}
                max={MAX_YEARS_EXPERIENCE}
                step={0.5}
                value={value.min_years_experience}
                disabled={disabled}
                onChange={(e) => set("min_years_experience", Number(e.target.value) || 0)}
              />
            )}
          </Field>

          <Field
            label="Reference"
            inline
            hint="Groups the ranking. Any stable identifier will do."
            error={errors?.job_id}
          >
            {(p) => (
              <TextInput
                {...p}
                value={value.job_id}
                invalid={Boolean(errors?.job_id)}
                disabled={disabled}
                onChange={(e) => set("job_id", e.target.value)}
                placeholder="j_nightsite"
              />
            )}
          </Field>
        </div>

        <div className="hairline" />

        <fieldset className="flex flex-col gap-2">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <legend className="text-2xs font-medium tracking-[0.07em] text-muted uppercase">
              Required certifications
            </legend>
            <span className="tabular text-2xs text-muted">
              {chosen}/{CERTIFICATIONS.length}
            </span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {CERTIFICATIONS.map((code) => (
              <Chip
                key={code}
                selected={value.required_certifications.includes(code)}
                onToggle={() => toggleCert(code)}
                note={
                  code === CRITICAL_CERTIFICATION
                    ? "Gates eligibility — its absence is scored differently"
                    : undefined
                }
              >
                {label(code)}
                {code === CRITICAL_CERTIFICATION && <span aria-hidden="true"> ★</span>}
              </Chip>
            ))}
          </div>
          <p className="text-2xs leading-relaxed text-muted">
            <span aria-hidden="true">★ </span>
            {label(CRITICAL_CERTIFICATION)} gates eligibility. Its absence is scored differently
            from a missing nice-to-have, through a feature of its own.
          </p>
        </fieldset>

        <Toggle
          checked={value.driving_required}
          onChange={(v) => set("driving_required", v)}
          label="A driving licence is required"
          hint="When it is not required, no candidate is penalised for lacking one."
        />
      </CardBody>
    </Card>
  );
}
