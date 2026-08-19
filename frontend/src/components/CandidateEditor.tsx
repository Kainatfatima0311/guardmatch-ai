"use client";

import clsx from "clsx";
import { useMemo, useRef, useState } from "react";
import {
  ACCEPTED,
  readAnyFiles,
  remainingCapacity,
  type CandidateDraft,
  type FileRejection,
} from "@/lib/files";
import { MAX_CV_LENGTH, MAX_RANK_BATCH } from "@/lib/types";
import { Button, Card, CardBody, CardHeader, Select, TextInput } from "./ui";

/**
 * The applications to rank.
 *
 * Three ways in, because the brief opens with SAJCO's hiring volume and only one
 * of them scales: paste, drop files, or generate a batch. Pasting is fine for
 * three applications and useless for three hundred.
 *
 * Both server-side limits are mirrored here — 20,000 characters per CV and 500
 * candidates per request — so a reviewer meets the ceiling while working rather
 * than after a submit comes back 422. Duplicate references are settled here for
 * the same reason: the service refuses the whole batch over one collision, which
 * is a slow way to learn that two files share a name.
 *
 * File names are shown and **never sent** — see the note in `@/lib/files`.
 *
 * ROWS ARE COLLAPSED UNLESS ASKED FOR
 *
 * The first version tracked which rows were *collapsed*, defaulting to none. That
 * is correct for three candidates and wrong for two hundred and fifty: loading a
 * batch rendered every row open, which is 250 textareas nobody asked to read, and
 * the posting scrolled out of reach.
 *
 * Inverted here — the set holds what is *expanded* — so any load path produces a
 * readable list without needing to remember to collapse. The one exception is a
 * row with no text yet: it is always open, because it exists to be typed into.
 */

/**
 * How many generated applications the control offers.
 *
 * It stops at 250 rather than the 500 the service accepts, because 500 is the
 * point at which the next request fails rather than a comfortable size to work at.
 */
export const DATASET_COUNTS = [10, 50, 100, 250] as const;

/** Above this the list gets a filter and its own scroll area. */
const LONG_LIST = 8;

export interface CandidateIssue {
  index: number;
  message: string;
}

export function validateCandidates(candidates: CandidateDraft[]): CandidateIssue[] {
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
      issues.push({ index, message: "Paste the application text, or drop a file." });
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

/** First meaningful line, so a collapsed row shows something recognisable. */
function preview(text: string): string {
  const line = text
    .split("\n")
    .map((l) => l.trim())
    .find((l) => l && !/^[A-Z][A-Z &]{2,}$/.test(l));
  return line ? (line.length > 64 ? line.slice(0, 64) + "…" : line) : "Empty";
}

export default function CandidateEditor({
  candidates,
  issues,
  disabled,
  onChange,
  onLoadSamples,
  onLoadDataset,
  loadingDataset,
}: {
  candidates: CandidateDraft[];
  issues: CandidateIssue[];
  disabled?: boolean;
  onChange: (next: CandidateDraft[]) => void;
  onLoadSamples: () => void;
  onLoadDataset: (count: number) => void;
  loadingDataset?: boolean;
}) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [datasetCount, setDatasetCount] = useState(100);
  const [dragging, setDragging] = useState(false);
  const [rejections, setRejections] = useState<FileRejection[]>([]);
  const [uploading, setUploading] = useState<{ done: number; total: number } | null>(null);
  const [query, setQuery] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);

  const update = (index: number, patch: Partial<CandidateDraft>) =>
    onChange(candidates.map((c, i) => (i === index ? { ...c, ...patch } : c)));

  const add = () => onChange([...candidates, { candidate_id: `c_${candidates.length + 1}`, cv_text: "" }]);

  const remove = (index: number) => onChange(candidates.filter((_, i) => i !== index));

  const clearAll = () => {
    onChange([{ candidate_id: "c_1", cv_text: "" }]);
    setExpanded(new Set());
    setQuery("");
    setRejections([]);
  };

  /**
   * Keyed by reference rather than by position, so expanding a row and then
   * removing an earlier one does not silently expand a different candidate.
   */
  const toggle = (key: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  async function ingest(fileList: FileList | null) {
    if (!fileList || fileList.length === 0) return;

    const room = remainingCapacity(candidates.length);
    const files = Array.from(fileList);
    const overflow = files.length - room;

    setUploading({ done: 0, total: Math.min(files.length, room) });
    const { drafts, rejected } = await readAnyFiles(
      files.slice(0, room),
      candidates.map((c) => c.candidate_id.trim()),
      (done, total) => setUploading({ done, total }),
    );
    setUploading(null);

    if (overflow > 0) {
      rejected.push({
        filename: `${overflow} more file${overflow === 1 ? "" : "s"}`,
        reason: `Only ${MAX_RANK_BATCH.toLocaleString()} candidates fit in one request.`,
      });
    }

    setRejections(rejected);

    if (drafts.length > 0) {
      // Replace a lone empty starter row rather than leaving it above the dropped
      // files, where it would fail validation for nothing the reviewer did.
      const existing = candidates.length === 1 && !candidates[0]!.cv_text.trim() ? [] : candidates;
      onChange([...existing, ...drafts]);
    }
  }

  const atCapacity = candidates.length >= MAX_RANK_BATCH;
  const filled = candidates.filter((c) => c.cv_text.trim()).length;
  const fromFiles = candidates.filter((c) => c.fromFile).length;
  const isLong = candidates.length > LONG_LIST;

  /** Original indices kept, because update and remove address the real list. */
  const shown = useMemo(() => {
    const rows = candidates.map((candidate, index) => ({ candidate, index }));
    const q = query.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter(
      ({ candidate }) =>
        candidate.candidate_id.toLowerCase().includes(q) ||
        (candidate.displayName ?? "").toLowerCase().includes(q) ||
        candidate.cv_text.toLowerCase().includes(q),
    );
  }, [candidates, query]);

  return (
    <Card>
      <CardHeader
        step={2}
        title="The applications"
        subtitle={
          fromFiles > 0
            ? `${filled} of ${candidates.length} ready · ${fromFiles} from files`
            : `${filled} of ${candidates.length} ready. Drop files, paste text, or generate a batch.`
        }
        actions={
          <>
            <Button type="button" size="sm" onClick={onLoadSamples} disabled={disabled}>
              4 samples
            </Button>
            <div className="flex items-center gap-1.5">
              <Select
                aria-label="How many generated applications to load"
                className="w-auto py-1.5 text-xs"
                value={String(datasetCount)}
                disabled={disabled || loadingDataset}
                onChange={(e) => setDatasetCount(Number(e.target.value))}
                options={DATASET_COUNTS.map((n) => ({ value: String(n), label: String(n) }))}
              />
              <Button
                type="button"
                size="sm"
                onClick={() => onLoadDataset(datasetCount)}
                disabled={disabled || loadingDataset}
              >
                {loadingDataset ? "Generating…" : "Generate"}
              </Button>
            </div>
            <Button
              type="button"
              size="sm"
              variant="primary"
              onClick={add}
              disabled={disabled || atCapacity}
            >
              Add blank
            </Button>
          </>
        }
      />

      <CardBody className="flex flex-col gap-4">
        {/* The drop zone leads, because it is the intake path that scales. */}
        <div
          onDragOver={(e) => {
            e.preventDefault();
            if (!disabled) setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            if (!disabled) void ingest(e.dataTransfer.files);
          }}
          className={clsx(
            "rounded-lg border border-dashed px-4 py-5 text-center transition-colors",
            dragging ? "border-primary bg-primary-wash" : "border-border-strong",
          )}
        >
          <input
            ref={fileInput}
            type="file"
            multiple
            accept={ACCEPTED.join(",")}
            className="sr-only"
            disabled={disabled}
            onChange={(e) => {
              void ingest(e.target.files);
              e.target.value = "";
            }}
          />
          <p className="text-sm font-medium">
            Drop CV files here, or{" "}
            <button
              type="button"
              disabled={disabled}
              onClick={() => fileInput.current?.click()}
              className="text-primary underline underline-offset-2 hover:text-primary-hover"
            >
              choose files
            </button>
          </p>
          <p className="mx-auto mt-1.5 max-w-md text-xs leading-relaxed text-muted">
            {ACCEPTED.join(", ")}. Text files are read in your browser; PDF and Word are sent to
            the service to have their text extracted.
          </p>
          <p className="mx-auto mt-1 max-w-md text-2xs leading-relaxed text-muted">
            A scanned PDF has no text in it to read, and is refused rather than ranked as an
            empty CV.
          </p>
          {uploading && (
            <p className="tabular mt-2 text-xs text-primary">
              Extracting {uploading.done} of {uploading.total}…
            </p>
          )}
        </div>

        {rejections.length > 0 && (
          <div role="alert" className="rounded-lg border border-neg bg-neg-wash px-3.5 py-2.5">
            <p className="text-xs font-medium text-neg">
              {rejections.length} file{rejections.length === 1 ? "" : "s"} not added
            </p>
            <ul className="mt-1.5 flex flex-col gap-1">
              {rejections.map((r, i) => (
                <li key={i} className="text-xs leading-relaxed">
                  <span className="font-medium">{r.filename}</span>
                  <span className="text-muted"> — {r.reason}</span>
                </li>
              ))}
            </ul>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="mt-1.5"
              onClick={() => setRejections([])}
            >
              Dismiss
            </Button>
          </div>
        )}

        {isLong && (
          <div className="flex flex-col gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <TextInput
                type="search"
                aria-label="Filter the applications"
                placeholder="Filter by reference, file name or CV text…"
                value={query}
                disabled={disabled}
                onChange={(e) => setQuery(e.target.value)}
                className="min-w-48 flex-1"
              />
              <Button
                type="button"
                size="sm"
                onClick={() => setExpanded(new Set())}
                disabled={disabled || expanded.size === 0}
              >
                Collapse all
              </Button>
              <Button type="button" size="sm" variant="danger" onClick={clearAll} disabled={disabled}>
                Clear all
              </Button>
            </div>

            {/* Stated because it is the trap: a reviewer who filters to five
                candidates and presses Rank would otherwise expect five results. */}
            <p className="text-2xs text-muted">
              {query
                ? `Showing ${shown.length} of ${candidates.length}. Filtering changes this list only — all ${candidates.length} are ranked.`
                : `All ${candidates.length} will be ranked. Rows open on click.`}
            </p>
          </div>
        )}

        <div
          className={clsx(
            "flex flex-col gap-2",
            // Its own scroll area once long, so the posting and the Rank button
            // stay reachable instead of being pushed off the page.
            isLong && "max-h-140 overflow-y-auto pr-1",
          )}
        >
          {shown.length === 0 && (
            <p className="py-4 text-center text-sm text-muted">
              Nothing matches “{query}”.
            </p>
          )}

          {shown.map(({ candidate, index }) => {
            const mine = issues.filter((i) => i.index === index);
            const length = candidate.cv_text.length;
            const over = length > MAX_CV_LENGTH;
            const key = `${index}:${candidate.candidate_id}`;
            // A row with no text is always open: it exists to be typed into.
            const isOpen = expanded.has(key) || !candidate.cv_text.trim();
            const panelId = `cv-panel-${index}`;

            return (
              <div
                key={key}
                className={clsx(
                  "overflow-hidden rounded-lg border transition-colors",
                  mine.length ? "border-neg" : "border-border",
                )}
              >
                <div className="flex flex-wrap items-center gap-2 bg-surface-2 px-3 py-2">
                  <button
                    type="button"
                    aria-expanded={isOpen}
                    aria-controls={panelId}
                    onClick={() => toggle(key)}
                    disabled={!candidate.cv_text.trim()}
                    className="text-muted transition-colors hover:text-text disabled:opacity-40"
                    title={isOpen ? "Collapse" : "Expand"}
                  >
                    <span aria-hidden="true" className="text-xs">
                      {isOpen ? "▾" : "▸"}
                    </span>
                    <span className="sr-only">
                      {isOpen ? "Collapse" : "Expand"} application {index + 1}
                    </span>
                  </button>

                  {/* The file name, when there is one. Shown here and stripped
                      before anything is sent — see @/lib/files. */}
                  {candidate.displayName ? (
                    <span
                      className="min-w-0 flex-1 truncate text-xs font-medium"
                      title={candidate.displayName}
                    >
                      {candidate.displayName}
                    </span>
                  ) : (
                    <input
                      aria-label={`Reference for application ${index + 1}`}
                      value={candidate.candidate_id}
                      disabled={disabled}
                      onChange={(e) => update(index, { candidate_id: e.target.value })}
                      className="tabular w-28 shrink-0 rounded-md border border-border-strong bg-surface px-2 py-1 text-xs font-medium"
                    />
                  )}

                  {!candidate.displayName && !isOpen && candidate.cv_text.trim() && (
                    <span className="min-w-0 flex-1 truncate text-xs text-muted">
                      {preview(candidate.cv_text)}
                    </span>
                  )}

                  {candidate.displayName && (
                    <span className="tabular hidden shrink-0 text-2xs text-muted sm:inline">
                      {candidate.candidate_id}
                    </span>
                  )}

                  <span
                    className={clsx(
                      "tabular ml-auto shrink-0 text-2xs",
                      over ? "font-medium text-neg" : "text-muted",
                    )}
                  >
                    {length.toLocaleString()}
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

                {isOpen && (
                  <div id={panelId} className="px-3 pt-3 pb-3">
                    {candidate.displayName && (
                      <p className="mb-2 text-2xs text-muted">
                        Read from the file. Edit freely — the text below is what gets ranked, not
                        the file.
                      </p>
                    )}
                    <textarea
                      aria-label={`Application text for ${candidate.displayName || candidate.candidate_id || `application ${index + 1}`}`}
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
        </div>

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
