"use client";

import clsx from "clsx";
import { useState } from "react";
import { MAX_CV_LENGTH, MAX_RANK_BATCH, type Candidate } from "@/lib/types";
import { Button, Card, CardBody, CardHeader } from "./ui";

/**
 * The applications to rank.
 *
 * Both server-side limits are mirrored here — 20,000 characters per CV and 500
 * candidates per request — so a reviewer sees the ceiling while typing rather
 * than after a submit comes back 422. Duplicate references are caught for the
 * same reason: the backend rejects the whole batch over one collision, which is a
 * slow way to learn that two rows share a name.
 *
 * Each application collapses once it has content. With four CVs pasted in full
 * the page becomes a scroll wall and the posting scrolls out of sight, which is
 * the one thing a reviewer needs to keep in view while comparing.
 *
 * Input is raw text only, because the backend accepts raw text only. There is no
 * PDF upload and nothing here pretends otherwise: a file picker that silently
 * dropped formatting would be a worse lie than its absence.
 */

export interface CandidateIssue {
  index: number;
  message: string;
}

export function validateCandidates(candidates: Candidate[]): CandidateIssue[] {
  const issues: CandidateIssue[] = [];
  const seen = new Set<string>();

  candidates.forEach((c, index) => {
    const id = c.candidate_id.trim();
    if (!id) {
      issues.push({ index, message: "Needs a reference." });
    } else if (seen.has(id)) {
      issues.push({ index, message: `Reference "${id}" is already used above.` });
    } else {
      seen.add(id);
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

/** First non-empty line, so a collapsed row shows something recognisable. */
function preview(text: string): string {
  const line = text
    .split("\n")
    .map((l) => l.trim())
    .find((l) => l && !/^[A-Z][A-Z &]{2,}$/.test(l));
  return line ? (line.length > 72 ? line.slice(0, 72) + "…" : line) : "Empty";
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
  const [collapsed, setCollapsed] = useState<Set<number>>(new Set());

  const update = (index: number, patch: Partial<Candidate>) =>
    onChange(candidates.map((c, i) => (i === index ? { ...c, ...patch } : c)));

  const add = () => {
    onChange([...candidates, { candidate_id: `c_${candidates.length + 1}`, cv_text: "" }]);
    setCollapsed(new Set());
  };

  const remove = (index: number) => {
    onChange(candidates.filter((_, i) => i !== index));
    setCollapsed(new Set());
  };

  const toggle = (index: number) =>
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });

  const atCapacity = candidates.length >= MAX_RANK_BATCH;
  const filled = candidates.filter((c) => c.cv_text.trim()).length;

  return (
    <Card>
      <CardHeader
        step={2}
        title="The applications"
        subtitle={`${filled} of ${candidates.length} filled in. Plain text — the parser reads headings and bullet lists.`}
        actions={
          <>
            <Button type="button" size="sm" onClick={onLoadSamples} disabled={disabled}>
              Load samples
            </Button>
            <Button
              type="button"
              size="sm"
              variant="primary"
              onClick={add}
              disabled={disabled || atCapacity}
            >
              Add
            </Button>
          </>
        }
      />
      <CardBody className="flex flex-col gap-3">
        {candidates.map((candidate, index) => {
          const mine = issues.filter((i) => i.index === index);
          const length = candidate.cv_text.length;
          const over = length > MAX_CV_LENGTH;
          const isCollapsed = collapsed.has(index);
          const panelId = `cv-panel-${index}`;

          return (
            <div
              key={index}
              className={clsx(
                "overflow-hidden rounded-lg border transition-colors",
                mine.length ? "border-neg" : "border-border",
              )}
            >
              <div className="flex flex-wrap items-center gap-2 bg-surface-2 px-3 py-2">
                <button
                  type="button"
                  aria-expanded={!isCollapsed}
                  aria-controls={panelId}
                  onClick={() => toggle(index)}
                  className="text-muted transition-colors hover:text-text"
                  title={isCollapsed ? "Expand" : "Collapse"}
                >
                  <span aria-hidden="true" className="text-xs">
                    {isCollapsed ? "▸" : "▾"}
                  </span>
                  <span className="sr-only">
                    {isCollapsed ? "Expand" : "Collapse"} application {index + 1}
                  </span>
                </button>

                <input
                  aria-label={`Reference for application ${index + 1}`}
                  value={candidate.candidate_id}
                  disabled={disabled}
                  onChange={(e) => update(index, { candidate_id: e.target.value })}
                  className="tabular w-28 rounded-md border border-border-strong bg-surface px-2 py-1 text-xs font-medium"
                />

                {isCollapsed && (
                  <span className="min-w-0 flex-1 truncate text-xs text-muted">
                    {preview(candidate.cv_text)}
                  </span>
                )}

                <span
                  className={clsx(
                    "tabular text-2xs",
                    isCollapsed ? "" : "ml-auto",
                    over ? "font-medium text-neg" : "text-muted",
                  )}
                >
                  {length.toLocaleString()} / {MAX_CV_LENGTH.toLocaleString()}
                </span>

                <Button
                  type="button"
                  variant="danger"
                  size="sm"
                  onClick={() => remove(index)}
                  disabled={disabled || candidates.length === 1}
                  aria-label={`Remove application ${index + 1}`}
                >
                  Remove
                </Button>
              </div>

              {!isCollapsed && (
                <div id={panelId} className="px-3 pt-3 pb-3">
                  <textarea
                    aria-label={`Application text for ${candidate.candidate_id || `application ${index + 1}`}`}
                    value={candidate.cv_text}
                    disabled={disabled}
                    rows={8}
                    onChange={(e) => update(index, { cv_text: e.target.value })}
                    placeholder={
                      "PROFILE\nSecurity officer with 5 years of experience.\n\nCERTIFICATIONS\n- SIA licence\n- fire marshal\n\nAVAILABILITY\nAvailable for night shifts.\n\nEMPLOYMENT\nSite Officer, Acme Ltd (2024 - present) - construction site"
                    }
                    className="tabular w-full resize-y rounded-lg border border-border-strong bg-surface-2 px-3 py-2.5 text-xs leading-relaxed transition-colors placeholder:text-muted hover:border-primary"
                  />
                </div>
              )}

              {mine.map((issue, i) => (
                <p
                  key={i}
                  className="flex items-center gap-1.5 border-t border-neg/30 bg-neg-wash px-3 py-1.5 text-xs font-medium text-neg"
                >
                  <span aria-hidden="true">▲</span>
                  {issue.message}
                </p>
              ))}
            </div>
          );
        })}

        {atCapacity && (
          <p className="text-xs text-muted">
            Batch limit reached. The service refuses more than {MAX_RANK_BATCH.toLocaleString()} in
            one request.
          </p>
        )}
      </CardBody>
    </Card>
  );
}
