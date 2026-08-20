# GuardMatch AI — Frontend

**Companion to:** [architecture.md](architecture.md) · [api-reference.md](api-reference.md)
**Date:** 2026-08-20

This document covers the Rank workspace — one page, and the only page — and, more than the
page itself, the constraints it enforces in code rather than in prose. It also covers the colour
system, the accessibility decisions, and what was deliberately left unbuilt.

**It was briefly three pages.** A fairness dashboard and a model provenance page were built,
used, and then removed, because they were aimed at the wrong reader: this interface is for the
reviewer building a shortlist, and a reviewer does not consult an adverse impact ratio to do that.
The fairness position and the provenance evidence are still deliverables of this project — they
live in [the fairness report](fairness-report.md), [the model card](model-card.md), and two API
endpoints that a reviewer *of the project* can call. Section 11 records what that cost and what it
did not.

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
blocklist registers each with its mitigation. Those rows carry an amber **proxy** badge in the
contribution table, with the specific exposure on hover. Amber rather than a neutral grey because
the badge is a constraint on how the row should be read, which is exactly what amber is reserved
for. `shift_match` is the known worst case and is also
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

Every foreground is measured against **all four background layers it can sit on**, and the
figure recorded is the worst of them. Body text requires 4.5:1 under WCAG AA.

Backgrounds — dark: `--bg #08090C`, `--surface #0E1013`, `--surface-2 #14171B`,
`--surface-3 #1B1F24`. Light: `#F7F8F9`, `#FFFFFF`, `#F4F5F7`, `#EEF0F2`.

The **accent is unchanged**. The ground under it was replaced for the Console redesign: deeper,
less blue, and low enough in chroma that a single-pixel rule reads as structure rather than as
decoration. Changing the ground and keeping the accent is a deliberately narrow move — a violet
accent was built, measured and reverted at the user's direction earlier, so the hue is settled and
the surfaces were the part still open.

| Token | Dark | worst | Light | worst |
|---|---|---|---|---|
| `--text` | `#E6E8EC` | 13.50 | `#0D1013` | 16.70 |
| `--muted` | `#969CA7` | 6.00 | `#565C66` | 5.89 |
| `--primary` | `#14B8A6` | 6.65 | `#0F766E` | 4.79 |
| `--primary-hover` | `#2DD4BF` | 8.90 | `#115E59` | 6.64 |
| `--amber` | `#F59E0B` | 7.71 | `#A94D08` | 4.90 |
| `--pos` | `#34D399` | 8.61 | `#047857` | 4.80 |
| `--neg` | `#FB7185` | 6.15 | `#BE123C` | 5.50 |

**Measuring against the deepest surface rather than the page background is what makes this table
worth having, and it has now earned its keep twice.** The first draft of the original palette
failed in four places once the fourth layer was introduced: `--border-strong` at 2.86 and 2.51 on
the dark raised surfaces, light `--amber` at 4.18, and light `--border-strong` at 2.98.

The first draft of this ground failed once, and marginally, which is the more instructive case.
Light `--primary` landed on **exactly 4.50** against `--surface-3`, with `--pos` at 4.51 and
`--amber` at 4.60 behind it — three colours passing on a rounding. Lightening `--surface-3` from
`#E7E9EC` to `#EEF0F2` bought all three about 0.3 of headroom. Nothing was visibly wrong before
the change and nothing looks different after it, which is exactly why the figure has to be read
rather than eyeballed.

Semantic colours are also used as tints, so text on each tint was measured separately. The
tightest of the eight pairs is `--primary` on `--primary-wash` in light at **4.76**.

| On its own wash | Dark | Light |
|---|---|---|
| `--primary` | 6.06 | 4.76 |
| `--amber` | 8.20 | 5.22 |
| `--pos` | 8.31 | 4.84 |
| `--neg` | 6.68 | 5.43 |
| `--text` on any wash | ≥ 12.29 | ≥ 16.48 |

### Two border tokens, because one was not enough

A single `--border` measured about **1.3:1**. That is correct for a decorative edge and wrong for
the boundary of an input or a control, where WCAG 1.4.11 asks 3:1. Rather than darkening every
border and losing the quiet separation the design depends on, a second token carries control
boundaries:

| Token | Dark | Light | Used for |
|---|---|---|---|
| `--border` | `#23272E`, 1.27 | `#DFE1E5`, 1.31 | Panel edges, table rules — decorative |
| `--border-strong` | `#6B737F`, worst 3.46 | `#767C86`, worst 3.68 | Inputs, selects, buttons, switches |

**This distinction became load-bearing in the Console redesign rather than merely tidy.** Once
panels are defined by rules instead of by shadow, `--border` is doing structural work everywhere
and the temptation is to darken it so it "passes". It should not be darkened: 1.4.11 governs
control boundaries, not separators, and a page of 3:1 rules is a page of visible scaffolding.

The measured table is written into `globals.css` beside the values, so a change that breaks a
ratio is visible in the same file as the change.

### Type, rhythm and elevation

A six-step type scale with explicit line heights and a four-step radius scale. Six sizes is
enough for this interface; a scale with more steps than the design needs invites inconsistency.

**There are no elevation levels.** The three shadow tokens are `none`. A panel here is defined by
a rule, not by floating above the page, and on a near-black ground a shadow reads as a smudge
rather than as height. The tokens are kept rather than deleted so that a future design wanting
depth changes one place instead of thirty.

The radius scale was **re-cut** for Console rather than re-applied: 0.125, 0.25, 0.375 and 0.5rem,
down from 0.375 to 1rem. Re-cutting the scale tightens every existing `rounded-*` usage at once,
which is both less churn and less risk than editing several dozen class names — and small radii
are most of what separates a tool from a consumer app.

Fonts are **self-hosted** through `next/font`, not linked from a CDN, and the reason is not
performance. A runtime request to `fonts.gstatic.com` would put a third party in the request
path of a hiring tool and leak that someone is using it. Verified: 13 `woff2` files emitted
locally, zero references to a font host in the served output.

Inter for prose, because it was designed for screen UI at small sizes. JetBrains Mono for
figures, because scores and contributions are read down a column and compared — with
proportional digits a 1 is narrower than a 7, the columns misalign, and the eye has to re-find
the decimal point on every row.

### Hierarchy, and what carries it

This section records two rounds, because the second one only makes sense against the first.

**Round one refined the design and the user's verdict was that nothing had changed.** That verdict
was correct, and it is the most useful thing in this document. Card headers became hairline rules,
a uniform spacing scale became a grouped one, a viewport breakpoint became a container query, and
a results header stopped competing with itself. Every one of those improved how the design worked.
None of them changed **what it was**: a card stack, in the same palette, at the same density, reads
as the same interface however much better it behaves.

**Round two changed the visual language instead of tuning it.** Direction chosen from four mockups:
Console — flat surfaces separated by single-pixel rules, small radii, dense rows, micro uppercase
labels, and every figure in mono. What follows is what that meant in practice, and the round-one
decisions that survived it are marked as such, because a decision that survives a redesign is
better evidence than one that has only ever been tested against the design it was made for.

**Card headers are a hairline rule, not a filled band** (round one, kept). The band used to sit on
`surface-2`, and it was asserting something untrue: a fill says the header is a different *kind* of
surface from the content, when all that is true is that one thing ends and another begins. A rule
says only the second.

**A panel's title is a micro label, not a heading** (round two, and the single biggest change here).
It is set as small tracked uppercase rather than as prose at `text-base`. A heading competes with
the content for the reader's first look; a label names a region and then gets out of the way. It
also buys back the vertical space that makes two hundred and fifty rows worth showing at all. The
step number went with it — mono and unboxed, because a filled badge was one more shape to parse
and the figure alone is enough to read three panels as a sequence.

That is also why `--border` at 1.3:1 is correct here rather than a failure. WCAG 1.4.11's 3:1
governs the boundary of a **control**, which is what `--border-strong` exists for. Darkening a
decorative rule to satisfy a criterion that does not apply to it would make every card heavier for
nothing.

**A row inside a card is tinted only while it is open.** With two hundred and fifty applications
loaded, a tinted strip per row would have left every row visually heavier than the section heading
above it, which is backwards. Collapsed rows sit on the card surface and are defined by their own
border; an open row gets a header band, because there it genuinely is the header of an open panel.

**Padding answers to the width it is given.** One fixed value from phone to monitor gives a wide
screen the gutter a narrow one needs, so the header and body step up at `sm`. Two values, not four:
a responsive scale nobody can hold in their head is a scale that drifts.

**Spacing carries the grouping** (round one, kept — with its own lesson attached). Every gap on
the page was `gap-6`, which means the layout made no claim at all: the posting, the note describing
what had just been loaded into it, the button that acts on it, and the results were each as related
to one another as any other pair. They are now one region held tight against wider gaps between
regions.

The absolute values changed in round two and the **ratio** did not, which is the point of having
written down that the ratio was the thing that mattered. The round-one numbers were chosen for a
looser design and would read as holes in this one.

**The posting form asked its own width, not the window's** — and then stopped needing to. Its
two-column grid was keyed to `sm:`, a *viewport* breakpoint, while the panel's width is set by the
grid column it sits in. Those are different questions that had been agreeing only by luck, and
introducing a two-column page layout at `md` broke the agreement at once: a 640px window with a
304px rail would have put two selects side by side inside 256px. The fix was a container query, and
it was right.

**It is retired now, because the layout it existed for is gone.** The posting is a definition list
— label in a fixed column, value beside it — which is one column at every width, so there is
nothing to switch. The explanation stays in the source so that whoever reintroduces a multi-column
grid there reaches for `@container` rather than for `sm:` and does not re-earn the same defect.

One instance was deliberately left on a viewport breakpoint, with a comment saying so: the reference
chip in a candidate row hides below `sm:`, and that still agrees with its column. The comment records
when it would need to change, because it is the kind of line someone corrects in the wrong direction.

**The applications are one table, not two hundred and fifty boxes.** Each row used to be its own
bordered, rounded box with a gap between them, which at 250 rows is five hundred borders and 250
gaps of nothing. One bordered container with hairline dividers carries the same information with a
fraction of the furniture, and it is what finally makes the list read as a list. A row with a
problem is marked by a left edge and a wash rather than by a full border — the only marker
available once rows share a frame, and better regardless, because the eye finds a broken vertical
line down a list faster than it finds one box among many.

**The drop zone is a strip.** It was a tall centred panel carrying three paragraphs, which is a lot
of furniture for a target you hit once, and in a dense list it was the largest thing on screen. The
sentence about scanned PDFs stays, because it is the one line there that prevents a silent wrong
ranking; it simply no longer occupies its own storey.

**The shortlist is a table, and the caveat became a column header.** This is the most useful thing
the redesign produced. Every score used to carry *"meaningful only within this posting, and not a
probability"* underneath it — 250 repetitions of one sentence, which is how a caveat becomes
wallpaper. It is now the score column's header, stated once, and still attached to every row as
`sr-only` text because a row read aloud on its own has no header above it. The constraint travels
with the number either way; it just stops shouting.

**The score still gets no bar, and a table invites one more than a card ever did.** A column of
figures looks unfinished without a sparkline beside it. It does not get one, for the reason in
section 3. The contribution bars inside an expanded row keep theirs, because a contribution really
is a magnitude within one explanation, measured against the largest in it — and that distinction
is written into the component so it does not have to be re-derived.

**Showing only the first reason per row was considered and rejected.** It would have saved more
height than anything else here, and it would have hidden two thirds of the plain-language layer
this interface exists to provide. `ReasonList` gained a dense mode instead — smaller type,
bullets rather than numbered chips — with every reason still rendered and nothing clamped.
**Density is bought by removing furniture, not by removing reasons.**

**Everything on the frame gave up a type size except the disclaimer.** The header, the footer, the
status line and the empty state all came down. The disclaimer strip kept `text-xs` and moved only
its padding: it is the one sentence that has to survive a partial read of the whole interface, so
winning vertical space there would be spending exactly the wrong thing.

**Two columns from `md`, with a narrower rail there.** Between 48rem and 64rem everything used to
stack into a single narrow column, wasting a tablet and a small laptop. The rail is 19rem at `md`
and 23rem at `lg`, because 23rem at `md` would leave the applications about 384px — phone width
on a landscape screen.

**One thing leads.** The results header was a heading on the left with three label-and-value pairs
and a button on the right, all at the same weight: four items with no order, while a reader takes
the heading first whatever the layout intends. The counts are subordinate now, and the export is the
only thing beside the heading, because it is the only action there.

Doing that surfaced a duplication worth more than the layout fix. The header read `Ranked 5` while
the status footer read `Applications 5` — **one figure under two names on one screen**, which
invites a reader to wonder whether they are different measurements. It was resolved by deciding
where the number belongs rather than by moving it: the count sits with the list, and the footer
reports only what answered, which is what it always said it was for.

**The rank action is deliberately not sticky.** The case for making it so was that loading 250
applications pushes it off screen. Measured, and it does not: the list caps itself at 35rem and
scrolls internally, so the tallest the applications card gets is about 758px and the action lands
near the fold rather than being pushed away. An element that can float over the shortlist is a worse
trade than one small scroll.


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
  The sign, the arrow and an `sr-only` phrase all state direction, so it is available three ways.
- **The step numbers are decoration, not a wizard.** The posting, the applications and the rank
  action are numbered 1–3 so three stacked cards read as a sequence rather than three unrelated
  panels. Nothing is gated on completing a step, because a reviewer may fill them in any order.
- **Pressing Rank with problems announces them.** The validation count renders into a
  `role="alert"` row, so it is spoken rather than only drawn.
- **Long CVs collapse.** With four applications pasted in full the page becomes a scroll wall and
  the posting scrolls out of view — the one thing a reviewer needs in sight while comparing. Each
  row collapses to its first meaningful line, with `aria-expanded` on the control.
- **No horizontal body scroll.** Wide content scrolls inside its own container.
- **Reduced motion honoured** via `prefers-reduced-motion`.

---

## 6. How applications get in

The brief opens with *"Given SAJCO's hiring volume"* — hundreds of applications per vacancy. The
first version of this interface required every CV to be pasted by hand, which is fine for three
and useless for three hundred. It did not match the premise it was built for.

Three paths now, and only one of them was expensive:

| Path | What it is for | Cost to build |
|---|---|---|
| **Drop files** | Real applications | `.txt` / `.text` / `.md` in the browser, `.pdf` / `.docx` through the service |
| **Generate a batch** | Seeing volume: 10 / 50 / 100 / 250 | `GET /sample-candidates`, labelled synthetic wherever it appears |
| **Paste** | One or two, or correcting extracted text | Already there |

### Two ways to read a file, and the reviewer sees neither

`.txt` needs nothing: `File.text()` reads it in the browser, so no request is made and no file
leaves the machine. `.pdf` and `.docx` cannot be read that way, so each one is sent to
`POST /extract` on drop and comes back as text.

`readAnyFiles` routes by extension across both paths and returns one list of candidates and one
list of problems. The split is invisible to whoever dropped the files, and it should be — they
dropped documents, and what they get back is candidates and, where something went wrong, the
reason.

**Extraction happens on drop, per file, not at ranking.** That is a design consequence of the
scanned-PDF case rather than an implementation detail: a reviewer needs to learn that a file is
unreadable while they are still handling files, not after submitting a batch of a hundred. The
cost is one request per document; the alternative is a batch result someone has to unpick.

**The extracted text is shown and editable before ranking.** A reviewer has to be able to see
what the extractor understood, and correct it, before a number is attached to a person. `source`
comes back with the text for the same reason — a PDF's reading order is a reconstruction, a
`.txt` is exactly itself, so one of them deserves a second look and the other does not.

### The display name never leaves the browser

A reviewer working through fifty applications cannot use `c_1, c_2, c_3`; they need to see which
file is which. But `name` is an **explicitly blocked attribute** in this system — it appears in
`features/blocklist.py` and in `_BLOCKED_TOKENS`, every request model is `extra="forbid"`, and
`assert_no_protected_fields` fires on anything reaching the feature builder. A name in a request
body would trip the leakage gate and fail the build.

So the two live in **different types**. `CandidateDraft` is what the interface holds and carries
`displayName`; `Candidate` is what crosses the network and cannot carry it.
`toRequestCandidates` is the single place the conversion happens, and a test asserts on the
serialised output that nothing else survives. Two types rather than one rule to remember.

Verified through the running stack, not only in a unit test: what the interface sends returns
**200**; the same body with `displayName` attached returns **422 `extra_forbidden`**; a literal
`name` field returns **422**. Two independent layers — the client strips it, and the service
would refuse it anyway.

Like an exam marked by roll number: the office knows which number belongs to which student, the
marker does not, and so the name cannot move the mark.

### What is refused, and why refusal is the point

| Input | Result |
|---|---|
| Empty file | **Refused.** An empty CV ranks last, so accepting one would show a confident bottom placement for a blank document |
| Over 20,000 characters | Refused, against the limit the service enforces |
| Too large to be a CV | Refused before it is read, against the same 5 MB limit the service enforces |
| **A scanned `.pdf`** | **Refused at the moment of upload.** See below |
| `.doc`, `.rtf`, `.odt`, `.pages` | Refused as **older formats, with the conversion named** — a reviewer told "unsupported" converts nothing |
| A file whose content does not match its name | Refused. The extension is a claim by whoever named the file; the first bytes are a claim by the file itself |

Failures are reported **per file**, not per drop: being told only that "something failed" after
dropping twenty files is not usable, and a reviewer needs to know which one to fix while they are
still holding it.

### The scanned PDF, which is the whole reason upload is careful

A scanned PDF has no text layer. `pypdf` returns an empty string from it and raises nothing —
because nothing went wrong, there simply is no text. Pass that on and it becomes an *empty CV*,
and an empty CV ranks last. The interface would show a confident bottom placement for a document
that could not be read, and the reviewer would see a weak candidate rather than an unreadable
file.

So it is refused where the file arrives, naming the cause and the way out: *"no text layer found
— this PDF looks scanned. Paste the text, or upload a .docx instead."*

**OCR was considered and rejected.** It is a large dependency, and mis-read text reproduces the
same silent wrong ranking in a new form: a CV whose certifications were garbled scores like one
that could not be read at all, except now nothing signals it. A refusal a reviewer can act on
beats an extraction nobody can check.

The empty-file refusal is the same argument at smaller scale, and it was written first.

### A list built for a hundred, not for three

Rows are **collapsed unless asked for**. The first version tracked which rows were *collapsed*,
defaulting to none — correct for three candidates and wrong for two hundred and fifty, where
loading a batch opened every row and pushed the posting off the page. Inverting it means any
intake path produces a readable list without anything having to remember to collapse it. A row
with no text yet is the exception: it is always open, because it exists to be typed into.

Past eight candidates the list gains a filter and its own scroll area, so the posting and the
Rank button stay reachable. **The filter states that it does not change what is ranked** —
*"Showing 12 of 250. Filtering changes this list only — all 250 are ranked."* That is the trap
the feature creates, and while the property is structural (the page submits the full list, and
the filtered view never reaches the request), a guarantee the user cannot see is not a guarantee
to them.

---

## 7. Reading the shortlist

Past eight candidates the results gain a filter, a sort and an export. All three are ways of
reading a ranking, and the interface is explicit that none of them is a way of *making* one.

### Filtering never renumbers a rank

The service ranked the whole batch. Hiding rows does not re-rank what is left, so row one of a
filtered list still reports its real position. A reviewer who narrows two hundred and fifty down
to twelve and reads "1" must not take it as "best of these twelve", so the count says it outright:

> *"Showing 12 of 250. Ranks are positions in the full shortlist, not in this view. Export writes
> all 250."*

Sorting by score is only a re-presentation of the order the service already assigned. The gap sort
tie-breaks by rank, so the same shortlist always presents the same way rather than depending on
whatever order the filter happened to produce. There is deliberately **no control that would
invite comparing across postings**, because the scores do not support it.

Filtering searches the display name as well as the reference — the reference is what the service
saw, the file name is what the reviewer recognises, and searching has to work on the one they can
read. The name still never leaves the browser.

### The export carries its own constraint

CSV export leads with the **disclaimer as its first row**, then the posting, the model version and
the request id. Same argument as the service shipping the disclaimer in every response: a
constraint that travels with the data cannot be left behind — and a CSV is exactly where a
ranking stops being a screen someone read carefully and becomes a column someone else sorts.

**It writes the whole shortlist, not the filtered view.** A file named "shortlist" that silently
held a fifth of one would be a different document wearing the same name. The filter note says so,
so the behaviour is not a surprise discovered after opening the file.

Fields are quoted per RFC 4180, because a reason containing a comma would otherwise shift every
later column by one and quietly corrupt the file it was exported to.

---

## 8. Boundary limits, mirrored client-side

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

## 9. Errors

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

## 10. Dependencies

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

## 11. Deliberately not built

Scope, not oversight.

| Not built | Why |
|---|---|
| **Fairness dashboard** | **Built, then removed.** It rendered `GET /fairness` faithfully, including the three verdict states and the caveats a pass needs. The problem was the audience: a recruiter working a shortlist does not need it, and a reviewer of the project is better served by [the fairness report](fairness-report.md), which can argue rather than only display. The endpoint remains, so nothing about the fairness position depends on the page having existed |
| **Model provenance page** | **Built, then removed**, for the same reason. `GET /model-info` and `GET /feature-importance` still answer from the running service, which is where the value actually was — the page was a rendering of it, not the thing itself |
| Parse playground | `POST /parse` exists and is worth showing, but the ranking flow already exercises the parser and surfaces its warnings |
| OCR for scanned PDFs | A large dependency whose failure mode is the one this project exists to prevent: mis-read text ranks confidently and wrongly, with nothing signalling it. Refused at upload instead — see section 6 |
| Authentication | No endpoint has any. Adding it to the frontend alone would imply protection that does not exist |
| Persisting a shortlist | Still not built, and the export does not change this. A CSV a reviewer chose to download is a working file; a stored ranking would be a record of a decision, and nothing here is one |
| Comparing two candidates side by side | Not in the brief, and it invites reading a score gap as a margin. The per-candidate contributions already answer "why this one and not that one" |
| Comparing across postings | Structurally excluded. The scores are relative to one posting, so a control offering it would imply a comparison the numbers cannot carry |

---

## 12. Known limitations

- **No end-to-end browser tests.** The API client, error normalisation, feature metadata and
  warning phrasings are unit tested; the rendered components are verified by hand. A Playwright
  suite is the obvious next step.
- **Contrast ratios are measured, colour vision deficiency is reasoned about.** The redundant
  sign-and-glyph encoding removes the dependency on hue, but no simulation was run.
- **One posting at a time.** No comparison across postings, which is consistent with the scores
  not being comparable across postings.
- **Two endpoints are no longer reachable from a browser.** `/fairness` and
  `/feature-importance` were removed from the proxy allowlist when the pages that used them were
  removed. They still answer on the API, and a server-side caller can still reach them. The
  allowlist is the browser's surface, and it should hold what a page needs rather than what the
  service happens to offer.
- **Upload is one request per document.** Twenty files means twenty round trips. That is the price
  of per-file refusal, and it was judged worth paying; a batch endpoint would be faster and would
  report failures worse.
- **The fairness page reads a recorded audit, not a live one.** It shows what was true of the
  evaluation set when the model was audited. It says nothing about the applications a reviewer
  ranked today, and does not claim to.
- **The thin sample CV reveals a model behaviour worth knowing.** A candidate who states a
  genuine mismatch can rank *below* one who states almost nothing, because a known-negative
  value is penalised harder than an unknown. See the model card's limitations.
