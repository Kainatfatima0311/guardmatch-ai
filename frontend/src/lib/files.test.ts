import { describe, expect, it } from "vitest";
import {
  MAX_FILE_BYTES,
  isBrowserReadable,
  isLegacy,
  needsServer,
  readAnyFiles,
  readTextFiles,
  referenceFromFilename,
  remainingCapacity,
  toRequestCandidates,
  type CandidateDraft,
} from "./files";
import { MAX_CV_LENGTH, MAX_RANK_BATCH } from "./types";

const txt = (name: string, body: string) => new File([body], name, { type: "text/plain" });

describe("toRequestCandidates", () => {
  it("strips the display name — the whole reason drafts are a separate type", async () => {
    // `name` is an explicitly blocked attribute in this system: it is in
    // features/blocklist.py and in _BLOCKED_TOKENS, every request model is
    // extra="forbid", and assert_no_protected_fields fires on anything reaching
    // the feature builder. A name in a request body would trip the leakage gate
    // and fail the build. So the reviewer sees it and the model never does.
    const drafts: CandidateDraft[] = [
      {
        candidate_id: "aisha_okafor_cv",
        cv_text: "PROFILE\nGuard with 6 years.",
        displayName: "Aisha Okafor CV.txt",
        fromFile: true,
      },
    ];

    const payload = toRequestCandidates(drafts);

    expect(Object.keys(payload[0]!).sort()).toEqual(["candidate_id", "cv_text"]);

    // Asserted on the serialised form too, because a leak would happen there and
    // a key check on the object can miss a nested one.
    const wire = JSON.stringify({ candidates: payload });
    expect(wire).not.toContain("Aisha Okafor");
    expect(wire).not.toContain("displayName");
    expect(wire).not.toContain("fromFile");
  });

  it("trims the reference, since it is compared for uniqueness server-side", () => {
    expect(toRequestCandidates([{ candidate_id: "  c_1  ", cv_text: "x" }])[0]!.candidate_id).toBe(
      "c_1",
    );
  });
});

describe("referenceFromFilename", () => {
  it("derives something readable and API-safe", () => {
    expect(referenceFromFilename("Aisha Okafor CV.txt", new Set())).toBe("aisha_okafor_cv");
  });

  it("keeps references unique, because one collision rejects the whole batch", () => {
    // The service enforces uniqueness within a request and refuses the entire
    // batch over a single duplicate. Two files named the same is ordinary, so
    // this is settled here rather than discovered in a 422.
    const taken = new Set<string>();
    const first = referenceFromFilename("cv.txt", taken);
    taken.add(first);
    const second = referenceFromFilename("cv.txt", taken);

    expect(first).toBe("cv");
    expect(second).toBe("cv_2");
  });

  it("survives a name with nothing usable in it", () => {
    expect(referenceFromFilename("###.txt", new Set())).toBe("cv");
  });

  it("keeps the whole name when there is no extension", () => {
    expect(referenceFromFilename("resume", new Set())).toBe("resume");
  });
});

describe("routing by extension", () => {
  it("sends text formats to the browser reader", () => {
    expect(isBrowserReadable("cv.txt")).toBe(true);
    expect(isBrowserReadable("CV.TXT")).toBe(true);
    expect(isBrowserReadable("cv.md")).toBe(true);
    expect(isBrowserReadable("cv.pdf")).toBe(false);
  });

  it("sends container formats to the service", () => {
    // A PDF or .docx needs a library that has no business in a browser bundle.
    expect(needsServer("cv.pdf")).toBe(true);
    expect(needsServer("cv.docx")).toBe(true);
    expect(needsServer("cv.txt")).toBe(false);
  });

  it("keeps older formats in their own category", () => {
    // Separate from "unsupported" on purpose: a reviewer told "unsupported"
    // converts nothing, told "save it as .docx" they know what to do.
    expect(isLegacy("cv.doc")).toBe(true);
    expect(isLegacy("cv.rtf")).toBe(true);
    expect(isLegacy("cv.docx")).toBe(false);
  });

  it("never puts a format in two buckets", () => {
    for (const name of ["a.txt", "a.md", "a.pdf", "a.docx", "a.doc", "a.rtf"]) {
      const buckets = [isBrowserReadable(name), needsServer(name), isLegacy(name)];
      expect(buckets.filter(Boolean)).toHaveLength(1);
    }
  });
});

describe("readAnyFiles", () => {
  it("reports legacy and unknown formats without touching the network", async () => {
    // Neither reaches `/extract`, so this runs with no fetch available at all —
    // which is itself the assertion: a `.doc` is refused locally, immediately.
    const { drafts, rejected } = await readAnyFiles([
      txt("cv.doc", "old"),
      txt("cv.png", "image"),
    ]);

    expect(drafts).toEqual([]);
    expect(rejected.map((r) => r.filename).sort()).toEqual(["cv.doc", "cv.png"]);
    expect(rejected.find((r) => r.filename === "cv.doc")!.reason).toContain("older format");
    expect(rejected.find((r) => r.filename === "cv.png")!.reason).toContain("not a CV format");
  });

  it("reads browser-readable files through the same call", async () => {
    const { drafts, rejected } = await readAnyFiles([txt("good.txt", "PROFILE\nSix years.")]);

    expect(rejected).toEqual([]);
    expect(drafts[0]!.candidate_id).toBe("good");
  });
});

describe("readTextFiles", () => {
  it("reads several files and names each after its file", async () => {
    const { drafts, rejected } = await readTextFiles([
      txt("first.txt", "PROFILE\nSix years."),
      txt("second.txt", "PROFILE\nThree years."),
    ]);

    expect(rejected).toEqual([]);
    expect(drafts.map((d) => d.candidate_id)).toEqual(["first", "second"]);
    expect(drafts[0]!.displayName).toBe("first.txt");
    expect(drafts[0]!.fromFile).toBe(true);
  });

  it("reports each failure separately rather than failing the whole drop", async () => {
    // Dropping twenty files and being told only that "something failed" is not
    // usable. A reviewer needs to know which file to fix while still holding it.
    const { drafts, rejected } = await readTextFiles([
      txt("good.txt", "PROFILE\nSix years."),
      txt("scan.pdf", "%PDF-1.4"),
      txt("blank.txt", "   \n  "),
    ]);

    expect(drafts).toHaveLength(1);
    expect(rejected.map((r) => r.filename)).toEqual(["scan.pdf", "blank.txt"]);
  });

  it("refuses an empty file instead of accepting it as an empty CV", async () => {
    // An empty CV ranks last, so accepting one would show a reviewer a confident
    // bottom placement for a file that was simply blank.
    const { drafts, rejected } = await readTextFiles([txt("blank.txt", "")]);

    expect(drafts).toEqual([]);
    expect(rejected[0]!.reason).toContain("empty");
  });

  it("refuses text over the character limit the service enforces", async () => {
    const { drafts, rejected } = await readTextFiles([
      txt("long.txt", "a".repeat(MAX_CV_LENGTH + 1)),
    ]);

    expect(drafts).toEqual([]);
    expect(rejected[0]!.reason).toContain(MAX_CV_LENGTH.toLocaleString());
  });

  it("refuses an oversized file before reading it", async () => {
    const { rejected } = await readTextFiles([txt("huge.txt", "a".repeat(MAX_FILE_BYTES + 1))]);

    expect(rejected[0]!.reason).toContain("too large");
  });

  it("does not collide with references already in the workspace", async () => {
    const { drafts } = await readTextFiles([txt("cv.txt", "PROFILE\nSix years.")], ["cv"]);

    expect(drafts[0]!.candidate_id).toBe("cv_2");
  });

  it("declines a PDF, because that is the router's job not this reader's", async () => {
    // `readTextFiles` reads what the browser can read. A `.pdf` arriving here means
    // the caller bypassed `readAnyFiles`, so the message describes a routing
    // mistake rather than telling a reviewer their file is wrong — they would go
    // and convert a file that is perfectly acceptable.
    const { drafts, rejected } = await readTextFiles([txt("cv.pdf", "%PDF")]);

    expect(drafts).toEqual([]);
    expect(rejected[0]!.reason).toContain("not read in the browser");
  });
});

describe("remainingCapacity", () => {
  it("counts down to the batch limit the service enforces", () => {
    expect(remainingCapacity(0)).toBe(MAX_RANK_BATCH);
    expect(remainingCapacity(MAX_RANK_BATCH)).toBe(0);
    expect(remainingCapacity(MAX_RANK_BATCH + 10)).toBe(0);
  });
});
