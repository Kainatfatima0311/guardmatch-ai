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
