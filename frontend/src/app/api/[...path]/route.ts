import { NextResponse, type NextRequest } from "next/server";
import { ALLOWED, REQUEST_ID_HEADER, upstreamUrl } from "@/lib/proxy";

/**
 * Server-side proxy to the scoring service.
 *
 * This exists so the browser never calls FastAPI directly. That is what lets
 * the backend keep its trust boundary: adding CORS middleware would have meant
 * naming every origin allowed to reach a hiring model, and getting that list
 * wrong later is a silent failure. Here there is no cross-origin request to
 * permit — the page and this handler share an origin, and the hop to FastAPI
 * happens server-side where the browser's rules do not apply.
 *
 * It forwards status and body unchanged. A proxy that flattens a 503 into a 500
 * or swallows a validation body would destroy exactly the information the UI
 * needs to tell a caller whether to fix their input or wait and retry.
 *
 * **Two defects lived here, and both were silent.** The handler hardcoded a JSON
 * Content-Type and read the body as text, which is fine for every JSON endpoint
 * and destroys a file upload: the multipart boundary was replaced and the binary
 * payload was decoded as UTF-8. Uploads failed with "field required" while the
 * identical request to the backend succeeded. A proxy should carry a request, not
 * interpret it.
 *
 * **The query string is forwarded too, and leaving it out was the other.**
 * The first version built the upstream URL from the path alone, so `?count=250`
 * was dropped in transit and the service answered with its default of 10. Nothing
 * errored: the caller asked for 250 applications, received 10, and was told
 * nothing about the difference. A proxy that silently discards half a request is
 * worse than one that fails, because the failure is invisible on both sides.
 */

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

// The allowlist and the upstream URL builder live in @/lib/proxy so they can be
// unit tested. See the note there: dropping the query string was a real defect.

async function forward(request: NextRequest, segments: string[]): Promise<NextResponse> {
  const path = segments.join("/");
  const allowedMethod = ALLOWED.get(path);

  if (!allowedMethod) {
    return NextResponse.json({ detail: `Unknown endpoint: /${path}` }, { status: 404 });
  }
  if (allowedMethod !== request.method) {
    return NextResponse.json(
      { detail: `/${path} does not accept ${request.method}` },
      { status: 405 },
    );
  }

  // The incoming Content-Type is forwarded, not replaced. Hardcoding JSON here
  // was a real defect: a multipart upload carries a boundary in its Content-Type,
  // and overwriting it left the service unable to find the file at all — every
  // upload came back "field required" while the same request straight to the
  // backend worked. The proxy must not have an opinion about the payload.
  const contentType = request.headers.get("Content-Type");
  const headers: HeadersInit = contentType ? { "Content-Type": contentType } : {};
  // Preserved rather than regenerated, so one id spans the browser, this
  // handler and the backend's structured logs. A support report quoting an id
  // then finds the exact log line.
  const requestId = request.headers.get(REQUEST_ID_HEADER);
  if (requestId) headers[REQUEST_ID_HEADER] = requestId;

  let upstream: Response;
  try {
    upstream = await fetch(upstreamUrl(BACKEND_URL, segments, request.nextUrl.search), {
      method: request.method,
      headers,
      // Raw bytes, not text. `request.text()` decodes as UTF-8, which mangles the
      // binary content of a PDF or .docx beyond recovery — the second half of the
      // same defect.
      body: request.method === "POST" ? await request.arrayBuffer() : undefined,
      cache: "no-store",
    });
  } catch {
    // The service is unreachable — not running, or the network dropped it.
    // 503 rather than 500 because the caller did nothing wrong and the same
    // request may well succeed once the service is back.
    return NextResponse.json(
      { detail: "The scoring service is unreachable." },
      { status: 503 },
    );
  }

  const text = await upstream.text();
  const response = new NextResponse(text, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("Content-Type") ?? "application/json" },
  });

  const upstreamId = upstream.headers.get(REQUEST_ID_HEADER);
  if (upstreamId) response.headers.set(REQUEST_ID_HEADER, upstreamId);

  return response;
}

type Context = { params: Promise<{ path: string[] }> };

export async function GET(request: NextRequest, context: Context): Promise<NextResponse> {
  return forward(request, (await context.params).path);
}

export async function POST(request: NextRequest, context: Context): Promise<NextResponse> {
  return forward(request, (await context.params).path);
}
