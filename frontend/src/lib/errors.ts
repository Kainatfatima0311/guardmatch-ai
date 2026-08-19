/**
 * One error shape for the UI, from several on the wire.
 *
 * The backend returns `422` from two different layers and they do not share a
 * body format:
 *
 *   Request validation  ->  detail is an ARRAY of {loc, msg, type, input}
 *   ParsingError        ->  detail is a STRING
 *
 * They differ because they mean different things. The first says the request
 * never matched the contract — a caller fixes the payload. The second says the
 * request matched and the content was still unusable — a caller fixes the CV.
 * A client that assumes either shape crashes on the other, so both are handled
 * here once, and the rest of the app sees only `NormalisedError`.
 *
 * `503` is separated out because it is the one status where the caller did
 * nothing wrong: the model has not finished loading or failed verification, and
 * the same request will succeed later. That distinction is the difference
 * between offering "try again" and offering "fix your input".
 */

export interface FieldError {
  /** Dotted path with FastAPI's leading "body" removed: `job.shift_pattern`. */
  path: string;
  message: string;
}

export interface NormalisedError {
  title: string;
  detail: string;
  /** True only when repeating the identical request could succeed. */
  retryable: boolean;
  fieldErrors: FieldError[];
  /** null when the request never reached the server at all. */
  status: number | null;
}

interface ValidationItem {
  loc?: unknown;
  msg?: unknown;
  type?: unknown;
}

const isRecord = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);

/**
 * FastAPI's `loc` is a tuple like ["body", "job", "shift_pattern"], and for a
 * list it contains numeric indices. The leading "body" is noise to a reader who
 * only ever sends a body.
 */
function formatLocation(loc: unknown): string {
  if (!Array.isArray(loc)) return "";
  const parts = loc
    .filter((p): p is string | number => typeof p === "string" || typeof p === "number")
    .map(String);
  const trimmed = parts[0] === "body" ? parts.slice(1) : parts;
  return trimmed.join(".");
}

function toFieldErrors(detail: unknown[]): FieldError[] {
  return detail.filter(isRecord).map((item: ValidationItem) => ({
    path: formatLocation(item.loc),
    message: typeof item.msg === "string" ? item.msg : "is not valid",
  }));
  // `input` is deliberately dropped. FastAPI echoes the offending value back,
  // and for a cv_text violation that is the entire CV — which would put the
  // document into an error banner, and into any screenshot of one.
}

export function normaliseError(status: number | null, body: unknown): NormalisedError {
  if (status === null) {
    return {
      title: "Could not reach the service",
      detail:
        "The request did not complete. The scoring service may be stopped, or the network dropped it.",
      retryable: true,
      fieldErrors: [],
      status: null,
    };
  }

  const detail = isRecord(body) ? body.detail : undefined;

  if (status === 422 && Array.isArray(detail)) {
    const fieldErrors = toFieldErrors(detail);
    const first = fieldErrors[0];
    return {
      title: "The request did not match the API contract",
      detail: first
        ? `${first.path || "request"} — ${first.message}`
        : "One or more fields were rejected.",
      retryable: false,
      fieldErrors,
      status,
    };
  }

  if (status === 422) {
    return {
      title: "A CV could not be read",
      detail:
        typeof detail === "string"
          ? detail
          : "The request was well formed but one of the CVs could not be parsed.",
      retryable: false,
      fieldErrors: [],
      status,
    };
  }

  if (status === 503) {
    return {
      // Covers both 503s a caller can see: the service is up but its model has
      // not loaded or failed checksum verification, and the service could not
      // be reached at all. Both mean "not now, try again", so the title is
      // shared and `detail` carries which one it was.
      title: "The scoring service is not available",
      detail:
        typeof detail === "string"
          ? detail
          : "The service has not finished loading and verifying its model.",
      retryable: true,
      fieldErrors: [],
      status,
    };
  }

  if (status === 500) {
    return {
      title: "The service reported a fault",
      detail:
        typeof detail === "string"
          ? detail
          : "An unexpected error occurred while scoring.",
      // Not retryable on purpose. A 500 here can mean the protected attribute
      // guard rejected the request, which is a defect to investigate rather
      // than a transient failure to retry.
      retryable: false,
      fieldErrors: [],
      status,
    };
  }

  return {
    title: `Unexpected response (${status})`,
    detail: typeof detail === "string" ? detail : "The service returned something unexpected.",
    retryable: status >= 500,
    fieldErrors: [],
    status,
  };
}
