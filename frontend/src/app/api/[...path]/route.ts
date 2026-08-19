import { NextResponse, type NextRequest } from "next/server";

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
 */

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

/**
 * Only the endpoints this interface uses. Without an allowlist the handler is
 * an open relay to anything the backend serves, reachable from any page that
 * can reach this one — including `/metrics`, which is operational data with no
 * business being exposed to a browser.
 */
const ALLOWED = new Map<string, "GET" | "POST">([
  ["rank", "POST"],
  ["score", "POST"],
  ["parse", "POST"],
  ["ready", "GET"],
  ["health", "GET"],
  ["model-info", "GET"],
]);

const REQUEST_ID_HEADER = "X-Request-ID";

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

  const headers: HeadersInit = { "Content-Type": "application/json" };
  // Preserved rather than regenerated, so one id spans the browser, this
  // handler and the backend's structured logs. A support report quoting an id
  // then finds the exact log line.
  const requestId = request.headers.get(REQUEST_ID_HEADER);
  if (requestId) headers[REQUEST_ID_HEADER] = requestId;

  let upstream: Response;
  try {
    upstream = await fetch(`${BACKEND_URL}/${path}`, {
      method: request.method,
      headers,
      body: request.method === "POST" ? await request.text() : undefined,
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
