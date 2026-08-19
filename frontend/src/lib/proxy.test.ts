import { describe, expect, it } from "vitest";
import { ALLOWED, upstreamUrl } from "./proxy";

const BACKEND = "http://api:8000";

describe("upstreamUrl", () => {
  it("forwards the query string — the regression this function exists for", () => {
    // The proxy originally built the URL from the path alone, so `?count=250` was
    // dropped and the service answered with its default of 10. Nothing errored:
    // the caller asked for 250 applications and silently received 10.
    expect(upstreamUrl(BACKEND, ["sample-candidates"], "?count=250")).toBe(
      "http://api:8000/sample-candidates?count=250",
    );
  });

  it("keeps every parameter, not just the first", () => {
    expect(upstreamUrl(BACKEND, ["sample-candidates"], "?count=50&seed=7")).toBe(
      "http://api:8000/sample-candidates?count=50&seed=7",
    );
  });

  it("adds nothing when there is no query string", () => {
    // A stray "?" would be harmless here but is exactly the kind of difference
    // that makes a logged URL not match the one that was requested.
    expect(upstreamUrl(BACKEND, ["ready"], "")).toBe("http://api:8000/ready");
  });

  it("preserves encoding rather than re-encoding it", () => {
    expect(upstreamUrl(BACKEND, ["parse"], "?q=a%20b")).toBe("http://api:8000/parse?q=a%20b");
  });
});

describe("ALLOWED", () => {
  it("covers every endpoint the client calls", () => {
    for (const path of ["rank", "sample-candidates", "ready", "model-info"]) {
      expect(ALLOWED.has(path), `${path} is not in the allowlist`).toBe(true);
    }
  });

  it("does not expose /metrics to a browser", () => {
    // Operational data with no business being reachable from a page. Asserted
    // rather than assumed, because an allowlist grows by accident.
    expect(ALLOWED.has("metrics")).toBe(false);
  });

  it("pins the method for each endpoint, so a GET cannot reach /rank", () => {
    expect(ALLOWED.get("rank")).toBe("POST");
    expect(ALLOWED.get("sample-candidates")).toBe("GET");
  });
});
