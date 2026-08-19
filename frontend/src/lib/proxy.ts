/**
 * Building the upstream URL for the server-side proxy.
 *
 * Extracted from the route handler so it can be tested. That is not tidiness for
 * its own sake: a defect lived in exactly this line. The first version built the
 * URL from the path alone, so `?count=250` was dropped in transit and the service
 * answered with its default of 10. Nothing errored — the caller asked for 250
 * applications, received 10, and was told nothing about the difference.
 *
 * A route handler is awkward to unit test; URL construction is trivial to. Moving
 * the fragile part into a pure function is what makes the regression assertable.
 */

/** Endpoints the proxy will forward, and the method each accepts. */
export const ALLOWED = new Map<string, "GET" | "POST">([
  ["rank", "POST"],
  ["score", "POST"],
  ["parse", "POST"],
  ["extract", "POST"],
  ["sample-candidates", "GET"],
  ["ready", "GET"],
  ["health", "GET"],
  ["model-info", "GET"],
]);

export const REQUEST_ID_HEADER = "X-Request-ID";

/**
 * The upstream URL for a proxied request.
 *
 * @param backendUrl Base URL of the scoring service, without a trailing slash.
 * @param segments   Path segments from the catch-all route.
 * @param search     The incoming query string, including its leading `?`, or "".
 */
export function upstreamUrl(backendUrl: string, segments: string[], search: string): string {
  return `${backendUrl}/${segments.join("/")}${search}`;
}
