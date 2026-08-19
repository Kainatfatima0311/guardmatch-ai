import { extractDocument } from "./api";
import { MAX_CV_LENGTH, MAX_RANK_BATCH, type Candidate } from "./types";

/**
 * Turning dropped files into candidates, in the browser.
 *
 * Two readers, and a router over them. `.txt`, `.text` and `.md` are read here
 * with `File.text()`, no server involved. `.pdf` and `.docx` go to `POST /extract`,
 * because pulling text out of a container format needs a library that does not
 * belong in a browser bundle.
 *
 * The split is invisible to a reviewer, and should be: they dropped files, and what
 * comes back is one list of candidates and one list of problems. `readAnyFiles` is
 * the router.
 *
 * THE DISPLAY NAME NEVER LEAVES THE BROWSER
 *
 * A reviewer working through fifty applications cannot use `c_1, c_2, c_3`; they
 * need to see which file is which. But `name` is an **explicitly blocked
 * attribute** in this system: it appears in `features/blocklist.py` and in
 * `_BLOCKED_TOKENS`, every request model is `extra="forbid"`, and
 * `assert_no_protected_fields` fires on anything reaching the feature builder.
 * Sending a name would trip the leakage gate and fail the build — which is the
 * mechanism working, not an obstacle to route around.
 *
 * So the two live in different types. `CandidateDraft` is what the interface
 * holds and carries the file name; `Candidate` is what crosses the network and
 * cannot carry it. `toRequestCandidates` is the one place the conversion happens,
 * and a test asserts its output has exactly two fields.
 *
 * Like an exam marked by roll number: the office knows which number belongs to
 * which student, the marker does not, and so the name cannot move the mark. A
 * name carries gender and ethnicity signal, and this project's central claim is
 * that the model cannot see either.
 */

/**
 * A file larger than this is refused before it is read.
 *
 * A CV is capped at 20,000 characters server-side, so a 2 MB text file cannot be
 * one — and reading it only to reject it wastes the reviewer's time and the
 * browser's memory. The allowance over `MAX_CV_LENGTH` is for multi-byte
 * characters: 20,000 characters of UTF-8 can exceed 20,000 bytes.
 */
export const MAX_FILE_BYTES = MAX_CV_LENGTH * 4;

/** Read in the browser with `File.text()`, no server involved. */
export const BROWSER_READABLE = [".txt", ".text", ".md"] as const;

/** Need server-side extraction: `POST /extract`. */
export const SERVER_READABLE = [".pdf", ".docx"] as const;

/** Everything the drop zone accepts. */
export const ACCEPTED = [...BROWSER_READABLE, ...SERVER_READABLE] as const;

/**
 * Older formats, named separately from "unsupported".
 *
 * A reviewer told "unsupported" converts nothing; told "save it as .docx" they
 * know exactly what to do. `.doc` is the old binary Word format and cannot be read
 * by anything here.
 */
export const LEGACY = [".doc", ".rtf", ".odt", ".pages"] as const;

/**
 * What the interface holds per application.
 *
 * `displayName` and `sourceFile` exist for the reviewer and are stripped before
 * anything is sent. Keeping them on a separate type is what makes that structural
 * rather than a rule someone has to remember.
 */
export interface CandidateDraft {
  candidate_id: string;
  cv_text: string;
  /** File name, or a name the reviewer typed. Browser-only. */
  displayName?: string;
  /** True when the text came from a file rather than being pasted. */
  fromFile?: boolean;
}

export interface FileRejection {
  filename: string;
  reason: string;
}

export interface ReadResult {
  drafts: CandidateDraft[];
  rejected: FileRejection[];
}

/** `report_2024.final.txt` -> `report_2024.final` */
function stripExtension(filename: string): string {
  const dot = filename.lastIndexOf(".");
  return dot > 0 ? filename.slice(0, dot) : filename;
}

function extensionOf(filename: string): string {
  const dot = filename.lastIndexOf(".");
  return dot >= 0 ? filename.slice(dot).toLowerCase() : "";
}

/**
 * A stable, API-safe reference derived from the file name.
 *
 * The service requires `candidate_id` to be unique within a request and rejects
 * the whole batch over one collision, so uniqueness is settled here rather than
 * discovered in a 422. Non-alphanumerics collapse to underscores, because the id
 * ends up in logs and in a CSV.
 *
 * @param taken Ids already in use, so two files named the same still differ.
 */
export function referenceFromFilename(filename: string, taken: Set<string>): string {
  const base =
    stripExtension(filename)
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "")
      .slice(0, 40) || "cv";

  if (!taken.has(base)) return base;

  let suffix = 2;
  while (taken.has(`${base}_${suffix}`)) suffix += 1;
  return `${base}_${suffix}`;
}

export function isBrowserReadable(filename: string): boolean {
  return (BROWSER_READABLE as readonly string[]).includes(extensionOf(filename));
}

export function needsServer(filename: string): boolean {
  return (SERVER_READABLE as readonly string[]).includes(extensionOf(filename));
}

export function isLegacy(filename: string): boolean {
  return (LEGACY as readonly string[]).includes(extensionOf(filename));
}

/**
 * Read dropped files into drafts, reporting each failure separately.
 *
 * Per-file rather than all-or-nothing: dropping twenty files and being told only
 * that "something failed" is not usable, and a reviewer needs to know *which*
 * file to fix while they are still holding it.
 *
 * @param files    What the drop or picker produced.
 * @param existing Ids already in the workspace, so references stay unique.
 */
export async function readTextFiles(
  files: File[],
  existing: Iterable<string> = [],
): Promise<ReadResult> {
  const taken = new Set(existing);
  const drafts: CandidateDraft[] = [];
  const rejected: FileRejection[] = [];

  for (const file of files) {
    if (!isBrowserReadable(file.name)) {
      // Anything needing the server is handled by `readServerFiles`, so reaching
      // here means the caller mixed the two lists up rather than that the file is
      // wrong. Named as a routing problem, not a user problem.
      rejected.push({
        filename: file.name,
        reason: `${extensionOf(file.name) || "This file"} is not read in the browser.`,
      });
      continue;
    }

    if (file.size > MAX_FILE_BYTES) {
      rejected.push({
        filename: file.name,
        reason: `${Math.round(file.size / 1024).toLocaleString()} KB is too large for a CV — the limit is ${MAX_CV_LENGTH.toLocaleString()} characters.`,
      });
      continue;
    }

    let text: string;
    try {
      text = await file.text();
    } catch {
      rejected.push({ filename: file.name, reason: "The file could not be read." });
      continue;
    }

    if (!text.trim()) {
      // Refused rather than accepted as an empty CV. An empty CV ranks last, so a
      // reviewer would be shown a confident bottom placement for a file that was
      // simply blank — the exact silent failure this project exists to avoid.
      rejected.push({ filename: file.name, reason: "The file is empty." });
      continue;
    }

    if (text.length > MAX_CV_LENGTH) {
      rejected.push({
        filename: file.name,
        reason: `${text.length.toLocaleString()} characters, over the ${MAX_CV_LENGTH.toLocaleString()} limit by ${(text.length - MAX_CV_LENGTH).toLocaleString()}.`,
      });
      continue;
    }

    const reference = referenceFromFilename(file.name, taken);
    taken.add(reference);

    drafts.push({
      candidate_id: reference,
      cv_text: text,
      displayName: file.name,
      fromFile: true,
    });
  }

  return { drafts, rejected };
}

/**
 * The only place a draft becomes a request payload.
 *
 * Returns exactly the two fields the API accepts. `displayName` and `fromFile`
 * are dropped here, and a test asserts on the serialised output that nothing else
 * survives — because the interesting failure is a field that leaks, and that
 * would happen in serialisation.
 */
export function toRequestCandidates(drafts: CandidateDraft[]): Candidate[] {
  return drafts.map((draft) => ({
    candidate_id: draft.candidate_id.trim(),
    cv_text: draft.cv_text,
  }));
}

/**
 * Send `.pdf` and `.docx` to the service, one call per file.
 *
 * Per file rather than batched, because the outcomes differ: a reviewer dropping
 * twenty documents needs to know which three failed, and why each one did. A
 * scanned PDF is the case that matters — it extracts to nothing, and the service
 * refuses it rather than returning an empty CV that would rank last.
 *
 * @param onProgress Called as each file settles, so the UI can report progress
 *   over a set of uploads that may take a few seconds.
 */
export async function readServerFiles(
  files: File[],
  existing: Iterable<string> = [],
  onProgress?: (done: number, total: number) => void,
): Promise<ReadResult> {
  const taken = new Set(existing);
  const drafts: CandidateDraft[] = [];
  const rejected: FileRejection[] = [];

  for (const [index, file] of files.entries()) {
    if (file.size > MAX_FILE_BYTES) {
      rejected.push({
        filename: file.name,
        reason: `${Math.round(file.size / 1024).toLocaleString()} KB is too large for a CV.`,
      });
      onProgress?.(index + 1, files.length);
      continue;
    }

    const result = await extractDocument(file);
    onProgress?.(index + 1, files.length);

    if (!result.ok) {
      rejected.push({ filename: file.name, reason: result.error.detail });
      continue;
    }

    const reference = referenceFromFilename(file.name, taken);
    taken.add(reference);

    drafts.push({
      candidate_id: reference,
      cv_text: result.data.cv_text,
      displayName: file.name,
      fromFile: true,
    });
  }

  return { drafts, rejected };
}

/**
 * Route a dropped set to the right reader and merge the outcomes.
 *
 * The split is invisible to a reviewer, and should be: they dropped files, some
 * needed the server and some did not, and what comes back is one list of
 * candidates and one list of problems.
 */
export async function readAnyFiles(
  files: File[],
  existing: Iterable<string> = [],
  onProgress?: (done: number, total: number) => void,
): Promise<ReadResult> {
  const legacy = files.filter((f) => isLegacy(f.name));
  const local = files.filter((f) => isBrowserReadable(f.name));
  const remote = files.filter((f) => needsServer(f.name));
  const unknown = files.filter(
    (f) => !isLegacy(f.name) && !isBrowserReadable(f.name) && !needsServer(f.name),
  );

  const localResult = await readTextFiles(local, existing);
  const taken = [...existing, ...localResult.drafts.map((d) => d.candidate_id)];
  const remoteResult = await readServerFiles(remote, taken, onProgress);

  return {
    drafts: [...localResult.drafts, ...remoteResult.drafts],
    rejected: [
      ...localResult.rejected,
      ...remoteResult.rejected,
      ...legacy.map((f) => ({
        filename: f.name,
        reason: `${extensionOf(f.name)} is an older format. Save it as .docx or .txt and try again.`,
      })),
      ...unknown.map((f) => ({
        filename: f.name,
        reason: `${extensionOf(f.name) || "This file"} is not a CV format. Accepted: ${ACCEPTED.join(", ")}.`,
      })),
    ],
  };
}

/** How many more files can be added before the batch limit is reached. */
export function remainingCapacity(current: number): number {
  return Math.max(0, MAX_RANK_BATCH - current);
}
