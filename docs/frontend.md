# GuardMatch AI — Frontend

**Companion to:** [architecture.md](architecture.md) · [api-reference.md](api-reference.md)
**Date:** 2026-08-19

This document covers the Rank workspace: what it is for, the constraints it enforces in code
rather than in prose, the colour system, the accessibility decisions, and what was deliberately
left unbuilt.

Paths are relative to `frontend/`.

---

## 1. Why it exists, given that it was once rejected

A frontend was a locked decision *against* — recorded in the design doc's rejected-options
table as "not requested in the brief; Swagger UI is sufficient for demonstration". That
reasoning was sound for the brief as written, and it has been left on the record rather than
edited away.

What changed is an observation about this system in particular. Its most distinctive output is
a per-candidate explanation that reconstructs the score it explains, additive to 1e-6. A
reviewer who is not reading JSON cannot see that at all. Swagger UI demonstrates that the
endpoint answers; it does not demonstrate what the answer is *for*. A shortlisting aid whose
explanations are unreadable by the person doing the shortlisting is only half delivered.

The reversal is deliberately narrow. One workspace, for the ranking flow. The service contract,
the model, and the fairness machinery are untouched.

---

## 2. The trust boundary, and why there is no CORS middleware

The browser never calls the FastAPI service. Every request goes to a route handler inside the
Next.js server, which makes the call onward.

```
browser ──► /api/rank  (Next.js, same origin) ──► FastAPI /rank
```

The alternative was adding `CORSMiddleware` to the backend, which means naming every origin
permitted to reach a hiring model — and getting that list wrong later is a silent failure that
widens access without anything appearing broken. The proxy removes the question instead of
answering it: there is no cross-origin request to permit, because the page and the handler share
an origin and the hop to FastAPI happens server-side where the browser's rules do not apply.

The backend is the audited artifact. It keeps the trust boundary it was reviewed with, and there
is no CORS configuration anywhere in the repository.

Two properties the handler has to preserve:

- **An endpoint allowlist.** Without one it is an open relay to everything the backend serves,
  reachable from any page that can reach this one — including `/metrics`, which is operational
  data with no business being exposed to a browser. `/api/metrics` returns 404 by design.
- **Status and body forwarded unchanged.** A proxy that flattens a `503` into a `500`, or
  swallows a validation body, destroys exactly the signal the UI needs to decide between "fix
  your input" and "wait and retry".

---

## 3. What this interface will not do

These are functional requirements, not styling preferences. Each is enforced in code.

### The score is never rendered as a proportion

No percentages, no rings, no progress bars, no "83% match". `relative_ranking_score` is printed
as a signed number next to its own name, with "this posting only" as persistent context.

Every one of those idioms implies a proportion of something, and reviewers read a filled ring as
"83% suitable" regardless of the caption beneath it. A LambdaRank output is an ordering within
one posting; it is not a probability and is not comparable across postings.

### A missing value is never rendered as zero

The parser records an unstated fact as `null` and refuses to infer "no" from silence. A CV that
never mentions driving shows **"not stated"**, not "no driving licence". Those are different
claims, and only the first one is true.

This is why one of the four sample CVs is deliberately thin: it returns seven `null` feature
values and four parse warnings. A demo built only from well-formed CVs would show an interface
that never has to admit it does not know something, and this rule would be untestable by eye.

### Parse warnings describe the document, not the applicant

"Did not say whether a driving licence is held", never "has no driving licence". The phrasings
live in `src/lib/warnings.ts` so they can be tested, and one of the tests asserts the rule
rather than the strings.

### The disclaimer comes from the response

`RankResponse.disclaimer` is rendered verbatim. The backend ships that text with every ranking
on purpose, so the constraint travels with the data rather than living only in documentation. A
second copy held in the client would be free to drift from it; there is nothing here to update
when the backend's wording changes.

### All twelve contributions are shown, including the ones that did nothing

The backend never truncates `contributions`. Omitting the near-zero rows would turn "this did
not matter" into "this was not considered" — different claims that a reader cannot tell apart
from an absence.

### The arithmetic is displayed, not asserted

SHAP here is additive: base value plus every contribution reconstructs the score. Each expanded
card prints `average + all 12 contributions = sum` against the reported score and marks whether
it matches. Measured across the sample set, deltas run from 0.0e+00 to 1.8e-15 — additivity
survives JSON rounding and the proxy hop intact.

An explanation that does not reconstruct the score it explains is a story printed beside a
number, and the interface should be able to say which one it is holding.

### Monitored proxy features are labelled where they act

Four of the twelve features can carry demographic information indirectly, and the project's own
blocklist registers each with its mitigation. Those rows are marked `(proxy)` in the contribution
table, with the specific exposure on hover. `shift_match` is the known worst case and is also
the model's single largest input. That fact previously lived only in the fairness report; it now
appears at the moment it is acting on a candidate.

---

## 4. The colour system — "Night Watch"

Colour carries meaning here rather than decorating. Three families are reserved, and nothing
else may use them:

| Token | Reserved for | Never used for |
|---|---|---|
| `--amber` | A constraint on how the output may be used — disclaimers, "not ready" | Generic warnings, highlights |
| `--pos` / `--neg` | The direction of a SHAP contribution | Success/error styling |
| `--primary` | Interactive affordances, and the leading candidate | Emphasis |

The reservation is what lets a reader learn the language once. A green badge that sometimes
means "saved" and sometimes means "counted in favour" teaches nothing.

### Palette and measured contrast

Every foreground/background pair was measured, not estimated. Body text requires 4.5:1 under
WCAG AA.

| Token | Dark | on `--bg` | on `--surface` | Light | on `--bg` | on `--surface` |
|---|---|---|---|---|---|---|
| `--text` | `#E6EDF7` | 15.89 | 14.45 | `#0F1B2D` | 16.25 | 17.28 |
| `--muted` | `#93A3BC` | 7.32 | 6.65 | `#5A6B85` | 5.09 | 5.42 |
| `--primary` | `#14B8A6` | 7.52 | 6.84 | `#0F766E` | 5.14 | 5.47 |
| `--amber` | `#F59E0B` | 8.72 | 7.93 | `#B45309` | 4.72 | 5.02 |
| `--pos` | `#34D399` | 9.74 | 8.86 | `#047857` | 5.15 | 5.48 |
| `--neg` | `#FB7185` | 6.96 | 6.33 | `#BE123C` | 5.91 | 6.29 |

Backgrounds: dark `--bg #0B1220`, `--surface #131C2E`; light `--bg #F6F8FB`, `--surface #FFFFFF`.

The tightest pair is amber on the light background at **4.72:1**, which clears AA. The loosest
is body text at 16.25:1.

### Two border tokens, because one was not enough

The first pass had a single `--border`, measured at **1.31:1**. That is correct for a decorative
card edge and wrong for the boundary of an input or a control, where WCAG 1.4.11 asks 3:1.
Rather than darkening every border and losing the quiet surface separation the design depends
on, a second token was added:

| Token | Dark | Light | Used for |
|---|---|---|---|
| `--border` | 1.31 | 1.32 | Card edges, table rules — decorative |
| `--border-strong` | `#566A92`, 3.14 | `#7E8899`, 3.58 | Inputs, selects, buttons, switches |

The measured table is written into `globals.css` beside the values, so a change that breaks a
ratio is visible in the same file as the change.

### Three theme states

An explicit choice stamps `data-theme` on the root element; the default "system" stamps nothing,
leaving `prefers-color-scheme` as the only signal. Each palette is therefore declared twice —
once under the media query and once under the attribute — so a toggle wins in both directions
rather than only when it agrees with the OS.

The toggle offers three options, not two. "System" is a real choice, and a two-way switch
destroys it the first time anyone clicks.

---

## 5. Accessibility

- **Direction never depends on colour alone.** Every contribution row carries a `+`/`−` sign and
  an arrow glyph alongside the emerald/rose fill, so the information survives greyscale
  printing, a poor projector, and colour vision deficiency.
- **Skip link first in the DOM.** Without it, reaching the applications means tabbing through
  nine certification chips and two selects on every visit.
- **One focus treatment, never removed.** A single `:focus-visible` rule, so a mouse click
  leaves no ring behind while keyboard navigation always shows where it is.
- **State exposed to assistive technology, not implied by styling.** `aria-pressed` on chips and
  theme buttons, `role="switch"` with `aria-checked` on the driving toggle, `aria-expanded` and
  `aria-controls` on the explanation disclosure.
- **One live region.** A single `aria-live="polite"` wrapper covers submitting, error, results
  and empty states, so a screen reader is told what happened once rather than having several
  regions compete.
- **The contribution table is a table.** `<th scope>` on both axes and an `sr-only` caption, so
  a row can be read as "Shift availability, 1.0, counted in favour" rather than as loose cells.
- **No horizontal body scroll.** Wide content scrolls inside its own container.
- **Reduced motion honoured** via `prefers-reduced-motion`.

---

## 6. Boundary limits, mirrored client-side

The server enforces these; the client repeats them so a reviewer meets the ceiling while typing
rather than after a submit comes back `422`.

| Limit | Value | Source |
|---|---|---|
| CV length | 20,000 characters | `parsing/patterns.py` |
| Batch size | 500 candidates | `core/config.py` |
| Minimum experience | 0–40 years | `schemas/job.py` |
| Unique `candidate_id` | enforced | `schemas/scoring.py` |

Form controls are generated from the closed vocabularies in `schemas/enums.py`, so the form
cannot offer a value the API would reject — every request model is `extra="forbid"`.

`shift_pattern` and `site_type` have **no default**, because they have none on the backend
either. Pre-selecting "day" and "retail" would mean every reviewer who did not look at those two
fields silently ranked against a posting the interface invented for them — and `shift_match` is
the model's largest single input.

---

## 7. Errors

`422` arrives in two incompatible shapes and both are handled in one place
(`src/lib/errors.ts`), because they mean different things:

| Source | `detail` | Means |
|---|---|---|
| Request validation | array of `{loc, msg, type}` | The request never matched the contract — fix the payload |
| `ParsingError` | string | The contract was met and the content is unusable — fix the CV |

`503` is separated out as the one status where the caller did nothing wrong, and is the only one
offered a **Try again**. It covers both an unverified model and an unreachable service; the
title is shared and `detail` says which.

FastAPI echoes the rejected value back in an `input` field. It is **dropped**, because on a
`cv_text` violation that field is the entire CV, and it would land in an error banner and in any
screenshot of one. A test asserts the CV text cannot appear in a serialised error.

Errors are returned, not thrown. A failed ranking is an ordinary outcome here — loading model,
oversized CV, missing field — and a thrown error invites one `catch` rendering one generic
message for six situations.

---

## 8. Dependencies

Next.js, React, and `clsx`. That is the whole runtime list.

No UI kit and no chart library. What this app needs is a form, a disclosure, and a horizontal
bar — and a bar is a `div` with a width. A kit would add a dependency tree larger than the
application it serves.

Next **16** rather than 15: a clean install of 15.5 reported three high-severity advisories in
its own dependency tree (`postcss` XSS and path traversal, `sharp`/libvips CVEs). Direct
exposure here is close to nil — the CSS is authored in this repository and no image optimisation
is used — but a project whose entire claim is that it verifies itself cannot hand a reviewer
three highs and an explanation. Next 16.3 reports zero.

---

## 9. Deliberately not built

Scope, not oversight.

| Not built | Why |
|---|---|
| Parse playground | `POST /parse` exists and is worth showing, but the ranking flow already exercises the parser and surfaces its warnings |
| Model provenance page | `/model-info` returns checksums, metrics and feature importance. Valuable, and not needed to demonstrate the ranking |
| Fairness dashboard | The audit output is not exposed by any endpoint; it would need either a new endpoint or reading `fairness.json`. The [fairness report](fairness-report.md) covers the substance |
| File upload | The backend accepts raw text only. A picker that silently dropped formatting would be a worse lie than its absence |
| Authentication | No endpoint has any. Adding it to the frontend alone would imply protection that does not exist |
| Saving or exporting shortlists | Nothing here is a record of a decision. Persisting a ranking would make it look like one |

---

## 10. Known limitations

- **No end-to-end browser tests.** The API client, error normalisation, feature metadata and
  warning phrasings are unit tested; the rendered components are verified by hand. A Playwright
  suite is the obvious next step.
- **Contrast ratios are measured, colour vision deficiency is reasoned about.** The redundant
  sign-and-glyph encoding removes the dependency on hue, but no simulation was run.
- **One posting at a time.** No comparison across postings, which is consistent with the scores
  not being comparable across postings.
- **The thin sample CV reveals a model behaviour worth knowing.** A candidate who states a
  genuine mismatch can rank *below* one who states almost nothing, because a known-negative
  value is penalised harder than an unknown. See the model card's limitations.
