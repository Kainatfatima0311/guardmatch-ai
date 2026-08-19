import { normaliseError, type NormalisedError } from "./errors";
import type {
  ModelInfoResponse,
  RankRequest,
  RankResponse,
  ReadyResponse,
  SampleCandidatesResponse,
} from "./types";

/**
 * The typed client.
 *
 * Every call goes to this app's own `/api/...` route handler, never to the
 * backend directly — see `src/app/api/[...path]/route.ts` for why.
 *
 * Errors are returned, not thrown. A failed ranking is an ordinary outcome of
 * this interface, not an exception: the model can be loading, a CV can be too
 * long, a field can be missing. Returning a result union forces each call site
 * to decide what to show, where a thrown error invites a `catch` that renders
 * one generic message for six different situations.
 */

export type Result<T> = { ok: true; data: T } | { ok: false; error: NormalisedError };

/** Correlates the browser, the proxy and the backend's logs. */
function newRequestId(): string {
  return globalThis.crypto.randomUUID().replace(/-/g, "");
}

async function call<T>(path: string, init?: RequestInit): Promise<Result<T>> {
  let response: Response;
  try {
    response = await fetch(`/api/${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        "X-Request-ID": newRequestId(),
        ...init?.headers,
      },
    });
  } catch {
    return { ok: false, error: normaliseError(null, null) };
  }

  // Read as text first. An upstream fault can return HTML or an empty body, and
  // response.json() would throw on both — turning a readable 502 into an
  // unreadable parse error.
  const text = await response.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = null;
    }
  }

  if (!response.ok) {
    return { ok: false, error: normaliseError(response.status, body) };
  }
  return { ok: true, data: body as T };
}

export function rank(request: RankRequest): Promise<Result<RankResponse>> {
  return call<RankResponse>("rank", { method: "POST", body: JSON.stringify(request) });
}

/**
 * Generated applications, so the ranking path can be tried at a realistic size.
 *
 * Available even while the model is still verifying, because the service produces
 * this without touching anything the model owns — a batch can be prepared before
 * it can be scored.
 */
export function sampleCandidates(
  count: number,
  seed?: number,
): Promise<Result<SampleCandidatesResponse>> {
  const query = new URLSearchParams({ count: String(count) });
  if (seed !== undefined) query.set("seed", String(seed));
  return call<SampleCandidatesResponse>(`sample-candidates?${query}`);
}

export function ready(): Promise<Result<ReadyResponse>> {
  return call<ReadyResponse>("ready");
}

export function modelInfo(): Promise<Result<ModelInfoResponse>> {
  return call<ModelInfoResponse>("model-info");
}
