# API Reference — GuardMatch AI

**Version:** 0.1.0
**Interactive docs:** `/docs` (Swagger UI) · `/redoc`
**Date:** 2026-08-17

```bash
uvicorn guardmatch.api.app:app --host 0.0.0.0 --port 8000
```

---

## Before anything else

**Scores are not probabilities.** A LambdaRank output is an uncalibrated number
meaningful only as an ordering *within one job posting*. It is not comparable across
postings, and it does not express a likelihood of being hired.

| Valid | Invalid |
|---|---|
| "Ranks 3rd of 40 for this posting" | "87% likely to be hired" |
| "Scored above candidate B here" | "Scored 2.97 out of 10" |

The field is named `relative_ranking_score`, every response repeats `score_type`, and
`/rank` returns a `disclaimer` field carrying the constraint with the data.

**This service ranks. It does not decide.** No endpoint returns an accept or reject verdict.
A human reviewer remains responsible for every hiring outcome.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/rank` | Rank many candidates against one job — **the primary endpoint** |
| POST | `/score` | Score one candidate against one job |
| POST | `/parse` | Extract structured facts from CV text |
| GET | `/sample-candidates` | Generate synthetic applications, for trying the service at volume |
| POST | `/extract` | Text out of one uploaded PDF, Word or plain-text document |
| GET | `/fairness` | The fairness audit carried by the active model |
| GET | `/feature-importance` | Which inputs move the ranking, across a sample |
| GET | `/health` | Liveness |
| GET | `/ready` | Readiness |
| GET | `/model-info` | Active model provenance |
| GET | `/metrics` | Prometheus exposition |

---

## POST /rank

The endpoint the system exists for. Ranking is a set operation — a candidate's position
depends on who else applied — so this is where the real answer comes from.

**Request**

```json
{
  "job": {
    "job_id": "j_demo",
    "required_certifications": ["security_licence", "fire_safety", "health_and_safety"],
    "min_years_experience": 4.0,
    "shift_pattern": "night",
    "site_type": "construction",
    "driving_required": true
  },
  "candidates": [
    { "candidate_id": "c_1", "cv_text": "PROFILE\nReliable security officer with 6 years..." },
    { "candidate_id": "c_2", "cv_text": "PROFILE\nSeeking a security position." }
  ]
}
```

**Response** `200`

```json
{
  "job_id": "j_demo",
  "score_type": "relative_ranking_score",
  "model_version": "v0.1.0",
  "request_id": "89916fe872604c1f8f7d1e0a2b3c4d5e",
  "candidates": [
    {
      "candidate_id": "c_1",
      "rank": 1,
      "relative_ranking_score": 2.9705,
      "score_type": "relative_ranking_score",
      "parse_warnings": [],
      "explanation": {
        "base_value": -2.0226,
        "contributions": [
          { "feature": "shift_match",        "value": 1.0,  "contribution": 0.9412 },
          { "feature": "cert_overlap_ratio", "value": 1.0,  "contribution": 0.8103 },
          { "feature": "exp_ratio",          "value": 1.0,  "contribution": 0.7216 },
          { "feature": "site_type_match",    "value": 1.0,  "contribution": 0.6390 },
          { "feature": "licence_match",      "value": 1.0,  "contribution": 0.5511 }
        ],
        "reasons": [
          "Available for the shift pattern this role needs — counted moderately in favour",
          "Holds 100% of the certifications this role requires — counted moderately in favour",
          "Experience is 1.5 times the stated minimum — counted moderately in favour",
          "Has prior experience at this type of site — counted moderately in favour",
          "Holds the required security licence — counted moderately in favour"
        ]
      }
    }
  ],
  "disclaimer": "Scores are relative to this job posting only and are not probabilities. This ranking is a shortlisting aid and is not a hiring decision; a human reviewer remains responsible for the outcome."
}
```

**Notes**

Candidates are ordered best fit first. Ties break by `candidate_id`, so an identical pair
does not reorder based on upload sequence.

>  **The `contributions` array above is abridged for readability. A real response is not.**
>  Every response carries **all 12 features, every time**, including those that contributed
>  nothing. Only `reasons` is a selection.

`contributions` is the auditable numeric record: all 12 features, ordered by absolute effect,
never filtered. A feature that scored zero is reported as zero rather than omitted, because
"this did not matter" and "this was not considered" are different claims and a reader cannot
tell them apart from an absence.

`reasons` is the plain-language rendering, and it *is* a selection: at most the top 5, with
any factor accounting for less than 2% of total absolute effect dropped as noise. So a
response can legitimately carry 12 contributions and 0 reasons — that happens when nothing
moved the candidate away from the average, and the array is then replaced by a single
sentence saying exactly that.

Both ship on every candidate; there is no flag to disable either.

`base_value + Σ contributions = relative_ranking_score`, exactly. Verified in tests to 1e-6.

Batch size is capped at `MAX_RANK_BATCH` (default 500) and rejected at the boundary.

**Measured latency:** 100 candidates in ~700 ms, including parsing, feature building,
scoring and SHAP explanation for all of them.

---

## POST /score

One candidate, one job. **Returns no rank** — a rank of 1 out of 1 would imply a comparison
that never happened. Use `/rank` when ordering matters.

**Request**

```json
{
  "job": { "job_id": "j_demo", "shift_pattern": "night", "site_type": "construction",
           "min_years_experience": 4.0, "required_certifications": ["security_licence"] },
  "candidate": { "candidate_id": "c_1", "cv_text": "PROFILE\n6 years of experience..." }
}
```

**Response** `200` — same shape as a ranked entry, minus `rank`, plus `job_id`.

---

## POST /parse

Extraction alone, no scoring. When a ranking looks wrong, the first question is almost always
whether the CV was read correctly; this answers it without a debugger.

**Response** `200`

```json
{
  "model_version": "v0.1.0",
  "profile": {
    "candidate_id": "c_1",
    "years_experience": 6.0,
    "certifications": ["fire_safety", "health_and_safety", "security_licence"],
    "driving_licence": true,
    "shift_availability": ["night", "rotating"],
    "site_experience": ["construction", "industrial"],
    "previous_role_count": 2,
    "months_since_last_role": 0,
    "parse_warnings": []
  }
}
```

### Three-state fields

`driving_licence` and `previous_role_count` distinguish three cases, and the difference
matters:

| Value | Meaning |
|---|---|
| `true` / a number | The CV states it |
| `false` / `0` | The CV states the negative — does not drive, no previous roles |
| `null` | **The CV never mentions it** |

Roughly a third of CVs never raise driving, and one in five has no employment section.
Treating that silence as a "no" would penalise candidates for what they omitted rather than
for what they lack. `years_experience` and `months_since_last_role` behave the same way.

A sparse CV therefore returns:

```json
{ "years_experience": null, "driving_licence": null, "previous_role_count": null,
  "parse_warnings": ["years_experience: not stated", "driving_licence: not stated",
                     "employment: no employment section found"] }
```

`parse_warnings` travel through to `/score` and `/rank`, so a reviewer can see where the
system was unsure rather than receiving a confident number built on a gap.

---

## GET /sample-candidates

Generated applications, so the ranking path can be exercised at the size the brief describes.
Pasting three hundred CVs by hand is not a way to see hiring volume.

| Parameter | Default | Notes |
|---|---|---|
| `count` | 10 | 1 to `MAX_RANK_BATCH`. Above that, `422` |
| `seed` | `RANDOM_SEED` | The same seed returns the same applications |

```bash
curl 'http://localhost:8000/sample-candidates?count=100'
```

```json
{
  "candidates": [
    { "candidate_id": "c_00000", "cv_text": "SUMMARY\nSecurity officer with 6 years..." }
  ],
  "count": 100,
  "seed": 42,
  "source": "synthetic"
}
```

**Notes**

**Generated, not read from disk.** The obvious implementation reads
`backend/data/candidates.json`, and it would fail in the container: `data/` is excluded from the
image deliberately, because a service that scores what it is sent has no use for the training
set. The generator ships inside the package instead, so this costs nothing at build time and
behaves identically locally, in the container and in CI. Roughly 80 ms for 250 candidates.

**Ground truth is stripped.** The generator produces candidates carrying the `true_*` values the
CV text was written from — years, certifications, availability. Returning those would hand a
caller exactly what the model is supposed to infer from the text, so only `candidate_id` and
`cv_text` cross the boundary.

**`source` travels with the data.** Stated in the payload rather than only here, for the same
reason `/rank` carries its disclaimer: a caller who never read this page still needs to know
these are not real applicants.

**No model required.** Unlike every scoring route, this does not return `503` while the model is
loading or unverified. It produces text and touches nothing the model owns, so a caller can
prepare a batch before the service is able to score it.

**`count` above the batch limit is refused here** rather than at `/rank`, so a caller is never
handed more candidates than it is allowed to submit.

---

## POST /extract

Text out of one uploaded document, so a CV can be dropped rather than pasted.

`multipart/form-data`, one field named `file`.

**One file per request, deliberately.** A reviewer dropping twenty documents needs to know
*which* three failed and why each one did; a batch endpoint either fails wholesale or returns a
mixed result the caller has to unpick anyway.

| Extension | Read by | Notes |
|---|---|---|
| `.txt` `.text` `.md` | Decoded directly | Accepted for completeness — the browser reads these without a request |
| `.pdf` | `pypdf` | Only with a text layer. See below |
| `.docx` | `python-docx` | Paragraphs **and table cells** |

```bash
curl -F file=@cv.pdf http://localhost:8000/extract
```

```json
{
  "filename": "cv.pdf",
  "cv_text": "SUMMARY\nSecurity officer with 6 years...",
  "characters": 1284,
  "source": "pdf"
}
```

**Notes**

**A scanned PDF is refused, and that refusal is why this endpoint has the shape it does.** A
scanned PDF has no text layer, so `pypdf` returns an empty string and raises nothing — because
nothing went wrong, there simply is no text. Passing that on produces an *empty CV*, and an empty
CV ranks last. The service would confidently place a candidate at the bottom of a shortlist
because their file could not be read, and the reviewer would see a weak candidate rather than an
unreadable document. That is precisely the silent failure this project exists to prevent, so it is
refused where the file arrives:

> `no text layer found — this PDF looks scanned. Paste the text, or upload a .docx instead.`

**OCR was considered and rejected.** It is a large dependency, and mis-read text reproduces the
same silent wrong ranking in a new form — a CV whose certifications were garbled scores like one
that could not be read at all, except now nothing signals it. A refusal a caller can act on is
worth more than an extraction nobody can check.

**Validated by extension *and* by content.** An extension is a claim made by whoever named the
file; the first bytes are a claim made by the file itself. A `.docx` that is really a PDF never
reaches a zip parser.

**Older formats are refused separately from unsupported ones.** A caller told "unsupported"
converts nothing; a caller told "save it as .docx" does.

**Table cells are read as well as paragraphs.** `python-docx` excludes table cells from
`paragraphs`, and in a formatted CV the certification list is usually a table — so reading only
paragraphs would silently drop the single most important thing the parser looks for.

**`source` travels with the text**, so a caller knows whether to expect layout damage. A PDF's
reading order is a reconstruction; a `.txt` is exactly itself.

**No model required.** Like `/sample-candidates`, this reads a file and touches nothing the model
owns, so it answers while the model is still verifying rather than returning `503`.

**Limits**

| | Limit | On breach |
|---|---|---|
| Upload size | 5 MB | Refused, stating the actual size |
| Extracted text | `MAX_CV_LENGTH`, 20,000 characters | **Refused, not truncated** — a CV cut mid-document parses as a CV missing whatever fell past the cut |

**Failures.** All `422` with a **string** `detail` — the `ParsingError` shape rather than the
array shape. See [Errors](#errors).

| Cause | `detail` |
|---|---|
| Empty file | `this file is empty` |
| PDF with no text layer | `no text layer found — this PDF looks scanned...` |
| Unsupported type | `.png is not supported. Accepted: .docx, .md, .pdf, .text, .txt.` |
| Older format | `.doc is an older format this cannot read. Save it as .docx or .txt and upload again.` |
| Content not matching the extension | Names the mismatch |

A missing `file` field is the *other* `422`: request validation, so `detail` is an array. A client
handling uploads has to read both shapes.

---

## Transparency endpoints

Two endpoints exist because the brief asks for a fairness check and for explainability, and
neither is much use if the only way to see it is to open a file in the repository. Both report what
the active model already carries; they compute no new claim about it.

**Neither is reachable from a browser through the shipped frontend.** A dashboard over them was
built and removed as aimed at the wrong reader, so they left the proxy's allowlist with it. They
are for a server-side caller, or for anyone inspecting the service directly — which is the
audience that was asking the question in the first place.

### GET /fairness

The audit recorded against the loaded model version.

```bash
curl http://localhost:8000/fairness
```

```json
{
  "model_version": "v0.1.0",
  "top_k": 10,
  "adverse_impact_threshold": 0.8,
  "max_gap": 0.1,
  "min_group_size": 30,
  "n_postings": 50,
  "n_rows": 3041,
  "passes": true,
  "failures": [],
  "inconclusive": [
    "age_band: adverse impact ratio 0.627 is below the four-fifths threshold of 0.80 — but not distinguishable from noise once corrected for 10 possible group comparisons (p=0.0069, threshold 0.0050); smallest group n=319"
  ],
  "attributes": [
    {
      "attribute": "gender",
      "groups": [
        {
          "group": "female",
          "n_appearances": 1275,
          "n_in_top_k": 214,
          "n_qualified": 428,
          "n_qualified_in_top_k": 191,
          "selection_rate": 0.1678,
          "qualified_selection_rate": 0.4463,
          "mean_exposure": 0.2391
        }
      ],
      "suppressed_groups": [],
      "adverse_impact_ratio": 0.9649,
      "demographic_parity_gap": 0.0059,
      "equal_opportunity_gap": 0.0389
    }
  ]
}
```

**Notes**

**Three states, not two.** `passes` alone is not enough to read this response, and a client that
branches on it will misreport. A non-empty `failures` is a fail; an empty `failures` with a
non-empty `inconclusive` means *cannot tell*, which is neither of the other two. `age_band` sits
at 0.627 — well below the 0.80 line — and is reported inconclusive rather than failing, because
after Bonferroni correction for ten possible group comparisons it is not distinguishable from
noise. Calling it a pass would be false; calling it a fail would be a claim the data does not
support.

**A pass is not evidence of fairness, and the audit's own numbers say so.** A deliberately
injected, realistically sized proxy bias passed at 0.875. The four-fifths rule is a floor, not a
target. Anything rendering this response should carry that beside the verdict rather than beneath
it.

**Demographics are synthetic and were never model inputs.** They exist in the evaluation set so
selection rates can be compared at all. Protected attributes are blocked at the request boundary
and again before the feature builder, so no result here can be read as the model having been told
and behaved well anyway.

**Suppressed groups are reported as suppressed**, not dropped. A group under `min_group_size` is
named in `suppressed_groups`, because a group too small to measure and a group that was never
there look identical if only the measurable ones are shipped.

| Status | When |
|---|---|
| `200` | Model loaded and the artifact carries an audit |
| `404` | The artifact carries no audit — `detail` names the command that produces one |
| `503` | Model not loaded, or checksums not yet verified |

### GET /feature-importance

Which inputs move the ranking, measured over a sample rather than asserted.

```bash
curl http://localhost:8000/feature-importance
```

```json
{
  "model_version": "v0.1.0",
  "sample_size": 200,
  "features": [
    { "feature": "shift_match", "mean_absolute_contribution": 0.9262, "share": 0.2627 },
    { "feature": "cert_overlap_ratio", "mean_absolute_contribution": 0.7265, "share": 0.2061 }
  ]
}
```

**Notes**

**Mean absolute SHAP contribution, not LightGBM split gain.** Gain counts how often the trees used
a feature; the SHAP mean counts how far it actually moved outputs. The second is the one that
answers "what is this ranking resting on".

**Absolute, so this is magnitude and not direction.** A feature that pushes some candidates up as
hard as it pushes others down is influential, and averaging signed values would hide it entirely.
Direction is a per-candidate question, and `/rank` answers it per candidate.

**All twelve features are returned, ordered by share**, including the ones that barely register. A
list trimmed to the top few would read as the whole model.

**The sample and the reference posting are fixed**, so two calls against a given model version
return the same figures. This is a property of the model, not of whatever traffic happened to
arrive.

**`shift_match` leads at 26.3%**, which is also the largest fairness exposure in the model — shift
availability correlates with caring responsibilities. Worth reading beside `/fairness` rather than
on its own.

**Computed once and cached** on first request. It is a few hundred SHAP evaluations, so the first
call is slower than the rest.

---

## Operational endpoints

### GET /health

Liveness. **Deliberately does not touch the model.** If it did, a model problem would restart
the container in a loop instead of removing the instance from the load balancer.

```json
{ "status": "ok" }
```

### GET /ready

Readiness. `200` when the model is loaded and its checksums verified; `503` until then.

```json
{ "ready": false, "model_version": "v0.1.0", "detail": "checksum verification failed" }
```

Wire this to the container readiness probe. An instance that cannot verify its own model must
not receive traffic.

### GET /model-info

Which model produced a score — answerable from the running service, not only from the
repository.

```json
{
  "model_version": "v0.1.0",
  "trained_at": "2026-08-17T17:38:31.692768+00:00",
  "data_version": "1.0.0",
  "git_sha": "32db2090e8a160caf2ccbf10a728ae721a3d3b0c",
  "feature_names": ["exp_gap", "exp_ratio", "..."],
  "metrics": { "model_ndcg_at_10": 0.9042, "baseline_ndcg_at_10": 0.8043 }
}
```

### GET /metrics

Prometheus exposition. Includes request counts and latency by endpoint and status, rank batch
sizes, score distribution, per-field parse warning counts, the active model version as a
labelled gauge, and feature distribution snapshots for later drift comparison.

---

## Callers, and why there is no CORS middleware

Two kinds of caller are supported, and only one of them is a browser.

**A server-side integration** — an HR system, a script, a scheduled job — calls these endpoints
directly. Nothing here is specific to a browser.

**The Rank workspace** does not. It calls a route handler inside its own Next.js server, which
makes the onward call server-side:

```
browser ──► /api/rank  (Next.js, same origin) ──► FastAPI /rank
```

There is therefore **no `CORSMiddleware` anywhere in this service, by design**. The alternative
was naming every origin permitted to reach a hiring model, which fails silently once that list
is wrong: access widens and nothing appears broken. The proxy removes the question rather than
answering it, because there is no cross-origin request to permit.

Consequences a caller should know:

- **Calling the API directly from browser JavaScript will be blocked**, and this is intended.
  Either proxy it server-side, or add CORS deliberately, with the origin list treated as a
  security decision rather than a configuration detail.
- **The proxy carries an endpoint allowlist**: `/rank`, `/score`, `/parse`, `/extract`,
  `/sample-candidates`, `/ready`, `/health`, `/model-info`. `/metrics` is deliberately not
  reachable through it — operational data has no business being exposed to a browser, and
  neither are `/fairness` and `/feature-importance`, which no page renders. An unlisted path
  returns `404`; a wrong method `405`. **The list holds what a page needs, not what the service
  offers** — which is why removing two pages removed two entries.
- **Status and body are forwarded unchanged.** A proxy that flattened a `503` into a `500` would
  destroy the distinction between "wait and retry" and "fix your input", which is the most
  useful thing the error surface carries.
- **`X-Request-ID` is preserved, not regenerated**, so one identifier spans the browser, the
  handler and this service's logs.

See [the frontend notes](frontend.md) for the client side.

## Errors

| Status | Meaning |
|---|---|
| `422` | Validation failure — malformed body, unknown enum, empty CV, oversized batch, duplicate candidate ids, unknown field |
| `503` | Model not loaded or not verified. **Retryable** — the caller did nothing wrong |
| `500` | Unexpected fault, including a protected attribute reaching the feature layer |

Rejection happens at the boundary, before any work begins.

**A `422` arrives in one of two shapes, and a client must handle both.** They come from
different layers, which is why they do not share a format:

| Source | `detail` is | Example |
|---|---|---|
| Request validation — malformed body, unknown enum, unknown field | an **array** of objects with `loc`, `msg`, `type` | `{"detail": [{"loc": ["body", "job", "shift_pattern"], "msg": "Input should be 'day', 'night', 'weekend' or 'rotating'", "type": "enum"}]}` |
| `ParsingError` — CV empty after stripping, or over 20,000 characters | a **string** | `{"detail": "CV text for candidate c_1 exceeds 20000 characters"}` |

The first is FastAPI reporting that the request never matched the contract. The second is the
contract having been met and the content still being unusable. Collapsing them would lose
that distinction, which is the one a caller needs in order to know whether to fix the payload
or fix the CV.

`extra="forbid"` on every request model means an unrecognised field is refused rather than
silently ignored. That is what stops a caller from attaching a demographic field to a
candidate payload and assuming it was considered — or assuming it was not.

A `500` from the protected attribute guard is a **defect in the system**, not a bad request.
It is logged at error level and should be investigated, not retried.

---

## Observability

Every request carries a correlation id, taken from an inbound `X-Request-ID` header when
supplied — so a trace can span services — and generated otherwise. It is returned in the
response header, echoed in `/score` and `/rank` bodies, and attached to every log line for
that request.

That id is what makes "why was this candidate ranked ninth on the 14th" an answerable
question.

Logs are structured JSON. **No request body is ever logged**, and 22 field names are redacted
recursively, because logs are retained longer and read more widely than the data they
describe.

---

## Configuration

Set by environment variable; see `backend/.env.example`.

| Variable | Default | Effect |
|---|---|---|
| `MODEL_VERSION` | `v0.1.0` | Which artifact to serve. Rollback is a change to this value |
| `MODEL_DIR` | `models` | Artifact root |
| `MAX_RANK_BATCH` | `500` | Maximum candidates per `/rank` request |
| `LOG_LEVEL` | `INFO` | — |
| `LOG_FORMAT` | `json` | `console` for readable local output |
| `API_HOST` / `API_PORT` | `0.0.0.0` / `8000` | Bind address |

Requesting a version that does not exist fails at startup with the available versions listed,
rather than falling back to a default. Silently serving a model the operator did not ask for
would be worse than refusing to start.
