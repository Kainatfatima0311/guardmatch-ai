# GuardMatch AI — Rank workspace

The interface for the scoring service. Drop a folder of CVs, or generate a couple of hundred, and
get a ranked shortlist where every placement carries the reasons behind it.

For what the project is, see the [root README](../README.md). The design decisions behind this half
— the colour system with its measured contrast ratios, the constraints enforced in code rather than
in prose, why the score is never shown as a percentage, and why there is no CORS middleware
anywhere in the backend — are in [the frontend notes](../docs/frontend.md).

## Running it

Requires **Node 22** and a running API. From this directory:

```bash
npm ci
npm run dev
```

Then <http://localhost:3000>. Press **Load samples** to try it without supplying real CVs, or
**Generate** a batch of 10 to 250 synthetic applications to see it at the volume the brief
describes.

The API is expected at `http://localhost:8000`. Point elsewhere with `BACKEND_URL`:

```bash
BACKEND_URL=http://localhost:9000 npm run dev
```

Or run both halves together with one command from the repository root:

```bash
docker compose up --build
```

## Checks

```bash
npm run lint
npm run typecheck    # separate from the build: Next can emit a working bundle with wrong types
npm test             # 93 tests
npm run build
```

The tests cover the API contract, both `422` body shapes, file intake and its two size bounds,
shortlist filtering and CSV export, the proxy's allowlist and query handling, and the requirements
derivation. The rendered components are verified by hand — there is no browser test suite, which is
listed as a known limitation in [the frontend notes](../docs/frontend.md).

## How applications get in

Three paths, and the reviewer sees one list of candidates from all three:

| Path | What happens |
|---|---|
| **Drop files** | `.txt`, `.text`, `.md` are read in the browser, so the file itself is never uploaded. `.pdf` and `.docx` go to `POST /extract` and come back as text you can read and edit before ranking |
| **Generate a batch** | 10 to 250 synthetic applications from `GET /sample-candidates`, labelled synthetic wherever they appear |
| **Paste** | For one or two, or to correct text read from a file |

**A scanned PDF is refused when it is dropped, not ranked.** It has no text layer, so it would
extract to nothing, and an empty CV ranks last — the system would place a candidate at the bottom
because their file could not be read. `.doc` and `.rtf` are refused too, naming the conversion.

## Layout

```
src/
├── app/
│   ├── layout.tsx          frame, metadata, no-flash theme bootstrap
│   ├── page.tsx            the workspace — holds the draft posting and the applications
│   ├── globals.css         design tokens, with every contrast ratio measured
│   └── api/[...path]/      server-side proxy — the reason no CORS config exists
├── components/
│   ├── Shell               page frame: rail, top bar, disclaimer strip, footer
│   ├── Rail                brand, the one destination, live model status, counts
│   ├── Steps               three-step header, derived from state, gating nothing
│   ├── JobForm             the posting — driven entirely by the backend's enums
│   ├── CandidateEditor     applications, with both server limits mirrored client-side
│   ├── RankResults         the shortlist, with filter, sort and CSV export
│   ├── CandidateCard       one placement, expanding to the full breakdown
│   ├── ContributionBars    all 12 SHAP contributions, and the additivity check
│   ├── ReasonList          the plain-language layer, shown above the numbers
│   ├── ParseWarnings       what the CV did not say
│   ├── Disclaimer          rendered from the response, never from a copy
│   ├── StatusFooter        which model answered, and the request id to quote
│   ├── Avatar              initials from a name that never leaves the browser
│   ├── ThemeToggle         light, dark, system
│   └── ui                  panels, fields, controls, slider, chips, buttons
└── lib/
    ├── types.ts            the API contract, mirrored by hand
    ├── api.ts              the typed client
    ├── errors.ts           both 422 shapes and 503, normalised to one thing
    ├── proxy.ts            the endpoint allowlist and upstream URL construction
    ├── files.ts            file intake, routing by extension, two size bounds
    ├── requirements.ts     what a posting asked for, against what a CV showed
    ├── shortlist.ts        filter, sort, CSV export
    ├── features.ts         display names for the 12 features, and additivity
    ├── warnings.ts         parser warnings phrased as gaps in the document
    ├── samples.ts          four sample CVs, one deliberately thin
    └── status.tsx          two numbers the rail displays, and nothing more
```

## What this interface will not do

Seven constraints, each enforced in code rather than in a style guide. The reasoning for all of
them is in [the frontend notes](../docs/frontend.md); the short version:

1. **The score is never rendered as a proportion.** No rings, no bars, no "83% match". A LambdaRank
   output is an ordering within one posting and carries no such quantity.
2. **A missing value is never rendered as zero.** The parser records an unstated fact as `null` and
   refuses to infer "no" from silence. A CV that never mentions driving shows "not stated".
3. **No match level.** "Strong match" would be a threshold the interface invented; the badge counts
   the posting's own requirements instead, and an unstated one never counts as a failure.
4. **Parse warnings describe the document, not the applicant.** "The CV did not state years of
   experience", never "no experience".
5. **The disclaimer comes from the response body**, so it cannot drift from what the service said.
6. **All twelve contributions are shown**, including the ones that did nothing. A trimmed list
   reads as the whole model.
7. **The arithmetic is displayed, not asserted.** The panel prints base value plus twelve
   contributions against the reported score, and says whether they agree.

The candidate's name is part of this: it is shown on screen and is **never sent**. `name` is a
blocked attribute in the backend, so the display name and the request payload are separate types
and the service would refuse it anyway.

## Dependencies

Next.js, React and `clsx`, with Vitest for tests. No UI kit and no chart library: what this needs
is a form, a disclosure and a horizontal bar, and a bar is a `div` with a width. Fonts are
self-hosted by `next/font` rather than linked from a CDN, so no third party sits in the request path
of a hiring tool.
