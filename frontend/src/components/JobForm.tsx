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
import { Card, Chip, Field, Select, TextInput, Toggle } from "./ui";

/**
 * The posting being ranked against.
 *
 * Every control is driven by the closed vocabularies in
 * `backend/src/guardmatch/schemas/enums.py`, so the form cannot offer a value
 * the API would reject — the request models are `extra="forbid"` and the enums
 * are exhaustive, which makes an unrecognised value a 422 rather than a
 * near-miss the backend quietly tolerates.
 *
 * `shift_pattern` and `site_type` have no default here because they have none
 * on the backend either. Pre-selecting "day" and "retail" would mean every
 * reviewer who did not look at those two fields silently ranked against a
 * posting the system invented for them.
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
const options = (values: readonly string[]) =>
  values.map((v) => ({ value: v, label: label(v) }));

/**
 * The form's own shape. `shift_pattern` and `site_type` widen to `""` because
 * "not yet chosen" is a real state in a form and is not a real state in the API
 * contract. Keeping them separate is what stops an unfilled select from being
 * submitted as though it were an answer.
 */
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

  return (
    <Card title="The posting" subtitle="What this vacancy actually needs.">
      <div className="flex flex-col gap-5">
        <Field label="Job reference" hint="Groups the ranking. Any stable identifier will do.">
          {(p) => (
            <TextInput
              {...p}
              value={value.job_id}
              disabled={disabled}
              onChange={(e) => set("job_id", e.target.value)}
              placeholder="j_nightsite"
            />
          )}
        </Field>

        <div className="grid gap-5 sm:grid-cols-2">
          <Field label="Shift pattern" error={errors?.shift_pattern}>
            {(p) => (
              <Select
                {...p}
                options={options(SHIFT_TYPES)}
                placeholder="Choose a shift"
                value={value.shift_pattern}
                disabled={disabled}
                onChange={(e) => set("shift_pattern", e.target.value as ShiftType)}
              />
            )}
          </Field>

          <Field label="Site type" error={errors?.site_type}>
            {(p) => (
              <Select
                {...p}
                options={options(SITE_TYPES)}
                placeholder="Choose a site type"
                value={value.site_type}
                disabled={disabled}
                onChange={(e) => set("site_type", e.target.value as SiteType)}
              />
            )}
          </Field>
        </div>

        <Field
          label="Minimum years of experience"
          hint={`0 to ${MAX_YEARS_EXPERIENCE}. Candidates below it are not excluded — the gap becomes one factor among twelve.`}
        >
          {(p) => (
            <TextInput
              {...p}
              type="number"
              min={0}
              max={MAX_YEARS_EXPERIENCE}
              step={0.5}
              className="sm:max-w-40"
              value={value.min_years_experience}
              disabled={disabled}
              onChange={(e) => set("min_years_experience", Number(e.target.value) || 0)}
            />
          )}
        </Field>

        <fieldset className="flex flex-col gap-2">
          <legend className="text-sm font-medium">Required certifications</legend>
          <p className="text-xs text-muted">
            {label(CRITICAL_CERTIFICATION)} gates eligibility — its absence is scored
            differently from a missing nice-to-have.
          </p>
          <div className="mt-1 flex flex-wrap gap-2">
            {CERTIFICATIONS.map((code) => (
              <Chip
                key={code}
                selected={value.required_certifications.includes(code)}
                onToggle={() => toggleCert(code)}
                note={code === CRITICAL_CERTIFICATION ? "Gates eligibility" : undefined}
              >
                {label(code)}
                {code === CRITICAL_CERTIFICATION && (
                  <span aria-label="gates eligibility" title="Gates eligibility">
                    {" "}
                    *
                  </span>
                )}
              </Chip>
            ))}
          </div>
        </fieldset>

        <Toggle
          checked={value.driving_required}
          onChange={(v) => set("driving_required", v)}
          label="A driving licence is required"
          hint="When it is not required, no candidate is penalised for lacking one."
        />
      </div>
    </Card>
  );
}
