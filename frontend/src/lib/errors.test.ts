import { describe, expect, it } from "vitest";
import { normaliseError } from "./errors";

describe("normaliseError", () => {
  it("reads the array-shaped 422 that request validation returns", () => {
    const body = {
      detail: [
        {
          type: "enum",
          loc: ["body", "job", "shift_pattern"],
          msg: "Input should be 'day', 'night', 'weekend' or 'rotating'",
          input: "nights",
        },
      ],
    };
    const e = normaliseError(422, body);

    expect(e.status).toBe(422);
    expect(e.retryable).toBe(false);
    expect(e.fieldErrors).toHaveLength(1);
    // The leading "body" segment is FastAPI's, not the caller's.
    expect(e.fieldErrors[0]?.path).toBe("job.shift_pattern");
    expect(e.detail).toContain("job.shift_pattern");
  });

  it("reads the string-shaped 422 that a parsing failure returns", () => {
    const e = normaliseError(422, {
      detail: "CV text for candidate c_1 exceeds 20000 characters",
    });

    expect(e.retryable).toBe(false);
    expect(e.fieldErrors).toEqual([]);
    expect(e.detail).toContain("exceeds 20000 characters");
  });

  it("never puts the rejected input into the message", () => {
    // FastAPI echoes the offending value back in `input`. For a cv_text
    // violation that is the whole CV, which must not reach an error banner or
    // a screenshot of one.
    const cv = "PROFILE\nSecret CV contents that must not be displayed.";
    const e = normaliseError(422, {
      detail: [{ type: "string_too_long", loc: ["body", "candidates", 0, "cv_text"], msg: "too long", input: cv }],
    });

    expect(JSON.stringify(e)).not.toContain("Secret CV contents");
    expect(e.fieldErrors[0]?.path).toBe("candidates.0.cv_text");
  });

  it("marks 503 retryable — the caller did nothing wrong", () => {
    const e = normaliseError(503, { detail: "model has not finished loading" });

    expect(e.retryable).toBe(true);
    expect(e.detail).toContain("model has not finished loading");
  });

  it("uses one 503 title for both an unloaded model and an unreachable service", () => {
    // The proxy returns 503 when it cannot reach the backend at all, and the
    // backend returns 503 when it is up but unverified. A title naming only the
    // model would be wrong for the first case.
    const unreachable = normaliseError(503, { detail: "The scoring service is unreachable." });
    const unverified = normaliseError(503, { detail: "checksum verification failed" });

    expect(unreachable.title).toBe(unverified.title);
    expect(unreachable.detail).toContain("unreachable");
    expect(unverified.detail).toContain("checksum");
    expect(unreachable.retryable).toBe(true);
  });

  it("marks 500 NOT retryable, because it can mean the protected attribute guard fired", () => {
    const e = normaliseError(500, {
      detail: "request rejected by the protected attribute guard",
    });

    expect(e.retryable).toBe(false);
  });

  it("handles a request that never reached the server", () => {
    const e = normaliseError(null, null);

    expect(e.status).toBeNull();
    expect(e.retryable).toBe(true);
  });

  it("survives a body that is not the shape any layer promised", () => {
    for (const body of [null, undefined, "plain text", 42, { unexpected: true }, []]) {
      const e = normaliseError(422, body);
      expect(typeof e.title).toBe("string");
      expect(typeof e.detail).toBe("string");
      expect(Array.isArray(e.fieldErrors)).toBe(true);
    }
  });
});
