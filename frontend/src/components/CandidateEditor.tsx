"use client";

import clsx from "clsx";
import { MAX_CV_LENGTH, MAX_RANK_BATCH, type Candidate } from "@/lib/types";
import { Button, Card } from "./ui";

/**
 * The applications to rank.
 *
 * The two server-side limits are mirrored here — 20,000 characters per CV and
 * 500 candidates per request — so a reviewer sees the ceiling while typing
 * rather than after a submit comes back 422. Duplicate candidate ids are caught
 * for the same reason: the backend rejects the whole batch over one collision,
 * which is a slow way to learn that two rows share a name.
 *
 * Input is raw text only, because the backend accepts raw text only. There is
 * no PDF upload and nothing here pretends otherwise; a file picker that silently
 * dropped formatting would be a worse lie than its absence.
 */

export interface CandidateIssue {
  index: number;
  message: string;
}

export function validateCandidates(candidates: Candidate[]): CandidateIssue[] {
  const issues: CandidateIssue[] = [];
  const seen = new Map<string, number>();

  candidates.forEach((c, index) => {
    const id = c.candidate_id.trim();
    if (!id) {
      issues.push({ index, message: "Needs a reference." });
    } else if (seen.has(id)) {
      issues.push({ index, message: `Reference "${id}" is already used above.` });
    } else {
      seen.set(id, index);
    }

    if (!c.cv_text.trim()) {
      issues.push({ index, message: "Paste the application text." });
    } else if (c.cv_text.length > MAX_CV_LENGTH) {
      const over = c.cv_text.length - MAX_CV_LENGTH;
      issues.push({
        index,
        message: `${over.toLocaleString()} characters over the ${MAX_CV_LENGTH.toLocaleString()} limit.`,
      });
    }
  });

  return issues;
}

export default function CandidateEditor({
  candidates,
  issues,
  disabled,
  onChange,
  onLoadSamples,
}: {
  candidates: Candidate[];
  issues: CandidateIssue[];
  disabled?: boolean;
  onChange: (next: Candidate[]) => void;
  onLoadSamples: () => void;
}) {
  const update = (index: number, patch: Partial<Candidate>) =>
    onChange(candidates.map((c, i) => (i === index ? { ...c, ...patch } : c)));

  const add = () =>
    onChange([...candidates, { candidate_id: `c_${candidates.length + 1}`, cv_text: "" }]);

  const remove = (index: number) => onChange(candidates.filter((_, i) => i !== index));

  const atCapacity = candidates.length >= MAX_RANK_BATCH;

  return (
    <Card
      title="The applications"
      subtitle={`${candidates.length} of up to ${MAX_RANK_BATCH.toLocaleString()}. Plain text — the parser reads headings and bullet lists.`}
      actions={
        <>
          <Button type="button" onClick={onLoadSamples} disabled={disabled}>
            Load samples
          </Button>
          <Button type="button" onClick={add} disabled={disabled || atCapacity}>
            Add application
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        {candidates.map((candidate, index) => {
          const mine = issues.filter((i) => i.index === index);
          const length = candidate.cv_text.length;
          const over = length > MAX_CV_LENGTH;

          return (
            <div
              key={index}
              className={clsx(
                "rounded-lg border p-3",
                mine.length ? "border-neg" : "border-border",
              )}
            >
              <div className="flex flex-wrap items-center gap-2">
                <input
                  aria-label={`Reference for application ${index + 1}`}
                  value={candidate.candidate_id}
                  disabled={disabled}
                  onChange={(e) => update(index, { candidate_id: e.target.value })}
                  className="rounded-md border border-border-strong bg-surface-2 px-2 py-1 text-sm font-medium"
                />
                <span
                  className={clsx("tabular ml-auto text-xs", over ? "text-neg" : "text-muted")}
                >
                  {length.toLocaleString()} / {MAX_CV_LENGTH.toLocaleString()}
                </span>
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => remove(index)}
                  disabled={disabled || candidates.length === 1}
                  aria-label={`Remove application ${index + 1}`}
                  className="px-2 py-1"
                >
                  Remove
                </Button>
              </div>

              <textarea
                aria-label={`Application text for ${candidate.candidate_id || `application ${index + 1}`}`}
                value={candidate.cv_text}
                disabled={disabled}
                rows={7}
                onChange={(e) => update(index, { cv_text: e.target.value })}
                placeholder={"PROFILE\nSecurity officer with 5 years of experience.\n\nCERTIFICATIONS\n- SIA licence"}
                className="mt-2 w-full resize-y rounded-lg border border-border-strong bg-surface-2 px-3 py-2 font-mono text-xs leading-relaxed placeholder:text-muted"
              />

              {mine.map((issue, i) => (
                <p key={i} className="mt-1.5 text-xs text-neg">
                  {issue.message}
                </p>
              ))}
            </div>
          );
        })}

        {atCapacity && (
          <p className="text-xs text-muted">
            Batch limit reached. The backend refuses more than{" "}
            {MAX_RANK_BATCH.toLocaleString()} in one request.
          </p>
        )}
      </div>
    </Card>
  );
}
