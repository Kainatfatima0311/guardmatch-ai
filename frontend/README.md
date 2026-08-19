# GuardMatch AI — Rank workspace

The interface for the scoring service: describe a posting, paste the applications, and get a
ranked shortlist where every placement carries the reasons behind it.

For what the project is, see the [root README](../README.md). The design decisions behind this
half — the colour system with its measured contrast ratios, the honesty rules below, and why
there is no CORS middleware anywhere in the backend — are recorded in the comments at the top
of the files that implement them, and collected in `docs/frontend.md`.

## Running it

Requires Node 22 and a running API. From this directory:

```bash
npm ci
npm run dev
```

Then <http://localhost:3000>. Press **Load samples** to try it without pasting real CVs.

The API is expected at `http://localhost:8000`. Point elsewhere with `BACKEND_URL`:

```bash
BACKEND_URL=http://localhost:9000 npm run dev
```

## Checks

```bash
npm run lint
npm run typecheck    # separate from the build: Next can emit a working bundle with wrong types
npm test             # 20 tests
npm run build
```

## Layout

```
src/
├── app/
│   ├── layout.tsx           frame, metadata, no-flash theme bootstrap
│   ├── page.tsx             the workspace — holds the draft posting and applications
│   ├── globals.css          Night Watch design tokens, with measured contrast ratios
│   └── api/[...path]/       server-side proxy to the scoring service
├── components/
│   ├── JobForm             the posting — driven entirely by the backend's enums
│   ├── CandidateEditor     applications, with both server limits mirrored client-side
│   ├── RankResults         the shortlist
│   ├── CandidateCard       one placement, with a disclosure for the numbers
│   ├── ContributionBars    all 12 SHAP contributions, and the additivity check
│   ├── ReasonList          the plain-language layer, shown above the numbers
│   ├── ParseWarnings       what the CV did not say
│   └── Disclaimer          rendered from the response, never from a copy
└── lib/
    ├── types.ts            the API contract, mirrored by hand
    ├── errors.ts           both 422 shapes and 503, normalised to one thing
    ├── features.ts         display names for the 12 features, and the additivity check
    ├── warnings.ts         parser warnings phrased as gaps in the document
    ├── samples.ts          four sample CVs, one deliberately thin
    └── api.ts              the typed client
```

## Two things this interface will not do

**It will not show the score as a percentage.** No rings, no progress bars, no "83% match".
A LambdaRank score is an ordering within one posting and carries no such quantity, and every
one of those idioms implies a proportion regardless of the caption beneath it.

**It will not render a missing value as zero.** The parser records an unstated fact as `null`
and refuses to infer "no" from silence. A CV that never mentions driving shows "not stated",
not "no driving licence" — those are different claims, and only the first one is true.

## Dependencies

Next.js, React, and `clsx`. No UI kit and no chart library: what this app needs is a form, a
disclosure and a horizontal bar, and a bar is a `div` with a width.
