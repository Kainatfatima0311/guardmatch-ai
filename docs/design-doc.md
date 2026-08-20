# GuardMatch AI — Design Document

**Project:** Resume Screening & Guard Job Matching Model
**Author:** Kainat Fatima
**Date:** 2026-08-15
**Status:** Draft for review — submitted before implementation begins
**Repository:** https://github.com/Kainatfatima0311/guardmatch-ai

Module and test paths in this document are shorthand relative to `backend/` —
`features/blocklist.py` means `backend/src/guardmatch/features/blocklist.py`.

---

## 1. Problem Statement and Goals

### 1.1 The problem

SAJCO hires security guards at volume. A single posting can attract several hundred
applications, and every one of them must be checked against the same set of hard
requirements: a valid security licence, a minimum number of years of experience, specific
certifications such as first aid or CCTV operation, and availability for the shift pattern
the site actually needs.

Doing this by hand has three costs:

- **Time.** Reading several hundred CVs against one job description takes days.
- **Inconsistency.** Two reviewers reading the same CV reach different conclusions, and so
  does the same reviewer on a Friday afternoon versus a Monday morning.
- **No audit trail.** When a candidate asks why they were not shortlisted, there is no
  record of the reasoning beyond a reviewer's memory.

### 1.2 What this system does

GuardMatch AI takes a set of candidate applications and one job posting, and returns the
candidates **ranked** by fit, each with an explanation of why they landed where they did.

It is a **shortlisting aid**. It orders a queue for a human reviewer.

### 1.3 Explicitly out of scope

This is the most important section of this document, because scope creep here has legal
consequences.

The system does **not**:

- Reject candidates automatically. It produces an ordering, not a decision.
- Make the final hire decision.
- Contact candidates or schedule interviews.
- Score candidates on anything other than the stated job requirements.

A human reviewer remains responsible for every hiring outcome. This constraint is repeated
in the model card and enforced in the API contract by returning ranks and explanations
rather than accept/reject verdicts.

### 1.4 Success criteria

| Dimension | Target | How it is measured |
|---|---|---|
| Ranking quality | NDCG@10 between 0.75 and 0.85 | Held-out job postings, grouped split |
| Beats naive baseline | LambdaRank NDCG@10 exceeds the rule-based baseline by a meaningful margin | Section 5.5 |
| Not degenerate | NDCG@10 **below 0.95** | Values above this indicate label leakage, not skill (Section 2.4) |
| Latency | p95 under 300 ms for a single score; under 2 s for a 100-candidate rank | Load test against the running API |
| Fairness | Adverse impact ratio at or above 0.80 for every measured group | Automated audit, enforced in CI |
| Explainability | Every returned candidate carries per-feature contributions | API contract test |

### 1.5 Measured results

Recorded here rather than adjusting the targets above, because moving a target after
seeing the number is how a project stops being able to tell whether it succeeded.

| Metric | Target | Measured (v0.1.0) | Verdict |
|---|---|---|---|
| NDCG@10 | 0.75–0.85 | **0.904** | Above the estimated band |
| Below circularity threshold | < 0.95 | 0.904 | Pass |
| Beats baseline | meaningful margin | 0.804 → 0.904, **+12.4%** | Pass |
| MAP | — | 0.899 (baseline 0.804) | — |
| MRR | — | 1.000 (baseline 0.964) | See below |

**On exceeding the band.** The 0.75–0.85 estimate was made before any data existed. The
measured 0.904 sits below the circularity threshold and the model clears the rule-based
baseline by ten NDCG points, so the result is not an artefact of label leakage. The more
likely explanation is that hidden factors carry only 20% of the label, leaving more
learnable structure in the visible features than the estimate assumed.

The honest reading is not "the model is excellent" but **"the synthetic task is easier than
real hiring"**. Real applications are messier, real reviewers less consistent, and real
outcomes depend on far more that never reaches a CV. This is recorded as a limitation in the
model card rather than presented as performance.

An MRR of exactly 1.000 supports that reading: the top-ranked candidate is genuinely
relevant in every one of the fifty validation postings. That is not a plausible outcome on
real data.

**A finding that changes Phase 9.** `shift_match` is the model's single most important
feature at **33.5% of total gain** — and it is also the proxy the bias injection exploits,
because availability correlates with caring responsibilities and therefore with gender.

The model is leaning hardest on precisely the feature most likely to carry demographic
information. Nothing has gone wrong: the feature is job-relevant and legitimately predictive.
But it means the fairness audit is not a formality here, and that removing the feature if it
fails would cost real ranking quality. That trade-off is now a known, documented decision
rather than a surprise.

---

## 2. Data Strategy

### 2.1 Why synthetic data

Real CVs cannot be used for this project:

- They contain personal data — names, addresses, dates of birth, employment history.
  Committing them to a public repository would be a privacy breach.
- Historical hire/reject labels are not available.
- Any real historical labels would carry whatever bias existed in past hiring decisions,
  and training on them would launder that bias into the model.

The project therefore generates its own dataset. This is a deliberate trade-off: it buys
privacy, reproducibility and a public repository at the cost of realism. Section 10 records
this as the project's single largest risk.

### 2.2 What gets generated

**Candidates** (target: 5,000)

| Field | Values |
|---|---|
| `years_experience` | 0–25, skewed towards the lower end |
| `certifications` | subset of: security licence, first aid, CPR, fire safety, CCTV operation, conflict management, dog handling, close protection, health & safety |
| `driving_licence` | boolean |
| `shift_availability` | subset of: day, night, weekend, rotating |
| `previous_roles` | 0–6 prior positions with dates |
| `cv_text` | free text assembled from templates with varied phrasing |

The `cv_text` field is the important one. It is generated from multiple phrasing templates
so that the parser is tested against genuine variation — "SIA licensed", "holds a valid
S.I.A. licence", "security licence (SIA), expires 2027" must all resolve to the same
canonical fact. A parser tested only against its own preferred phrasing proves nothing.

**Job postings** (target: 200)

| Field | Values |
|---|---|
| `required_certifications` | 1–4 certifications |
| `min_years_experience` | 0–10 |
| `shift_pattern` | day, night, weekend, rotating |
| `site_type` | retail, corporate, construction, event, residential, industrial |
| `description` | free text |

Each job posting becomes one **query group** for the ranking model (Section 5.2).

### 2.3 Relevance labels

LambdaRank needs graded relevance, not a binary flag. Each (candidate, job) pair receives a
label from 0 to 3:

| Label | Meaning |
|---|---|
| 3 | Strong fit — would be interviewed first |
| 2 | Good fit — would be interviewed |
| 1 | Marginal — only if the shortlist is thin |
| 0 | Not suitable |

### 2.4 Anti-circularity design

This is the central methodological risk of a synthetic-data project, and it is worth
stating plainly.

If the function that assigns labels uses the same variables that are later handed to the
model as features, then the model does not learn anything about hiring — it reverse-engineers
our own scoring rule. The result is an NDCG near 0.99 and a completely worthless model. The
evaluation would be measuring the generator, not the learner.

Four mitigations are built into the generator:

**(a) Hidden factors.** The label function includes variables that never become features —
a simulated interview performance score and a reference-check outcome. In real hiring these
factors matter and are invisible at CV-screening time, so their absence from the feature set
is realistic rather than artificial. They put an irreducible ceiling on achievable NDCG.

**(b) Label noise.** Between 10% and 15% of labels are perturbed by one grade. Real
reviewers are inconsistent; a dataset without noise is not a model of reality.

**(c) Non-linear interactions.** The label function contains interaction terms — for
example, a security licence contributes strongly only when paired with meaningful
experience, and shift mismatch penalties scale with site criticality. A purely additive
rule would be trivially recoverable by a linear model, which would make the choice of a
gradient-boosted ranker meaningless.

**(d) A sanity band on results.** If NDCG@10 comes out above 0.95, that is treated as a
**defect**, not a success. It means labels are leaking through the features and the
generator must be revised. The realistic target band is 0.75–0.85.

### 2.5 Deliberate bias injection

The generator includes a **switchable** bias mode, off by default and documented in the
data card.

When enabled, it introduces a correlation between a protected attribute and a legitimate-
looking feature — specifically, it makes night-shift availability correlate with one
demographic group, so that a model trained on this data will indirectly disadvantage the
other group through an apparently neutral feature.

The purpose is to prove the fairness suite works. A bias detector that has never fired on
known-biased data is not a detector; it is decoration. The audit in Section 7 must catch
this injected bias, and a test asserts that it does.

### 2.6 Protected attributes: separate storage

The generator produces protected attributes — gender, age, nationality — because fairness
cannot be measured without them. They are written to a **separate file**, loaded by a
separate module (`data/protected.py`), and the feature-building package does not import it.

This is an architectural barrier rather than a coding convention. The intent is that
including a protected attribute in the feature set would require someone to deliberately add
an import that does not currently exist, not merely to forget a rule.

### 2.7 Reproducibility

Every generation run is seeded. The data card records the seed, the generator version, the
row counts, and the resulting distributions, so any reported metric can be traced back to
the exact dataset that produced it.

---

## 3. NLP and Feature Extraction

### 3.1 Approach: rules, not embeddings

CV text is unstructured. The parser converts it into a strict, typed structure.

The chosen approach is **spaCy `EntityRuler` plus regular expressions plus fuzzy string
matching** (`rapidfuzz`). Sentence embeddings were considered and rejected.

| Criterion | Rules + fuzzy | Embeddings |
|---|---|---|
| Size | ~50 MB | ~500 MB, inflating the Docker image |
| Speed | milliseconds | tens of milliseconds, plus model load |
| Determinism | identical output for identical input | sensitive to model version |
| Auditability | every match traces to a named pattern | similarity score with no traceable cause |

The deciding factor is auditability. This system must be able to answer "why did you decide
this candidate holds a first-aid certificate?" with a specific pattern that matched a
specific span of text. A cosine similarity of 0.83 is not an acceptable answer in a hiring
context.

The domain also favours rules: the vocabulary of guard certifications is small, closed and
well known. This is not open-ended semantic matching.

An LLM-based parser was rejected for the same reasons, with the addition of cost and
non-determinism.

### 3.2 Normalisation

The hardest part of parsing is that one fact has many surface forms. `parsing/normalizers.py`
maps every observed variant to a canonical token:

```
"SIA", "S.I.A.", "sia licence", "security licence",
"security license", "SIA badge"        ->  CERT_SECURITY_LICENCE

"first aid", "first-aid", "FAW",
"emergency first aid at work"          ->  CERT_FIRST_AID
```

Fuzzy matching handles typos and spacing variants above a tuned similarity threshold; below
that threshold, no match is recorded. Silence is preferable to a wrong extraction.

### 3.3 Parser output

The parser emits a validated Pydantic model:

```python
class ParsedProfile(BaseModel):
    years_experience: float | None
    certifications: set[CertificationCode]
    driving_licence: bool
    shift_availability: set[ShiftType]
    previous_role_count: int
    months_since_last_role: int | None
    parse_warnings: list[str]
```

`None` is used deliberately where a field could not be extracted. Defaulting a missing
experience value to zero would silently penalise a candidate for a parsing failure, which is
a fairness problem disguised as a data-cleaning convenience. Missing values are passed
through to LightGBM, which handles them natively.

`parse_warnings` records anything ambiguous, and warnings surface in the API response so a
reviewer can see when the system was unsure.

---

## 4. Feature Engineering

### 4.1 Pairwise features

Features describe a **(candidate, job) pair**, not a candidate in isolation. The same
candidate is an excellent fit for one posting and a poor fit for another.

| Feature | Definition | Range |
|---|---|---|
| `exp_gap` | candidate experience minus job minimum | -10 to +25 |
| `exp_ratio` | candidate experience over job minimum, capped | 0 to 5 |
| `licence_match` | job requires a security licence and candidate holds one | 0 / 1 |
| `cert_overlap_ratio` | required certifications held, as a proportion | 0 to 1 |
| `cert_overlap_count` | required certifications held, absolute | 0 to 9 |
| `missing_critical_cert` | any mandatory certification absent | 0 / 1 |
| `shift_match` | candidate availability covers the job's shift pattern | 0 / 1 |
| `site_type_match` | prior experience at this site type | 0 / 1 |
| `driving_required_match` | job needs a driver and candidate drives | 0 / 1 |
| `extra_cert_count` | relevant certifications beyond those required | 0 to 9 |
| `role_count` | number of prior positions | 0 to 6 |
| `recency_months` | months since the most recent role | 0 to 240 |

### 4.2 Protected attribute blocklist

The following are never features, under any transformation:

gender, age, date of birth, graduation year, name, nationality, ethnicity, marital status,
photograph, postcode, and religion.

`features/blocklist.py` holds this list, and `tests/test_leakage.py` fails the build if any
blocked field reaches the feature builder.

### 4.3 Proxy risk register

Blocking direct attributes is not sufficient, because some permitted features leak protected
information indirectly. Each identified proxy is recorded with its mitigation:

| Feature | Leaks | Mitigation |
|---|---|---|
| `recency_months` | career breaks, which correlate with parental leave and therefore with gender | Capped and bucketed; monitored in the fairness audit |
| `role_count` | correlates with age | Capped at 6 |
| `exp_gap` | correlates with age | Retained — it is directly job-relevant and legally defensible — but monitored |
| `shift_match` | correlates with caring responsibilities, which correlate with gender | Monitored; this is the attribute the injected bias exploits |

The register is a living document. New features require a proxy assessment before they are
added.

### 4.4 Feature contract

`features/registry.py` owns the canonical feature name list and ordering, serialised to
`feature_names.json` alongside each model. Loading a model whose feature list disagrees with
the current code fails at startup.

Train/serve skew from silently reordered features is a classic and near-invisible production
failure, and this contract is what prevents it.

---

## 5. Ranking Model

### 5.1 Objective

LightGBM with `objective="lambdarank"`, optimising NDCG.

This is genuinely a ranking problem rather than a classification problem. HR does not need a
calibrated probability for each candidate in isolation; they need the right people at the top
of the list. LambdaRank optimises exactly that, by considering all candidates for a posting
together and learning which orderings score well.

### 5.2 Query grouping

Each job posting is one query group. LightGBM receives a `group` array giving the number of
candidates per posting.

**The train/validation split is performed at the group level, never at the row level.** A
row-level split would place some candidates for a posting in training and others in
validation, letting the model memorise that posting's characteristics. The reported metric
would be optimistic and wrong.

### 5.3 Evaluation

| Metric | What it captures |
|---|---|
| NDCG@5, NDCG@10 | Primary — graded relevance, position-discounted |
| MAP | Precision across the full ranking |
| MRR | How quickly the first strong candidate appears |
| Spearman correlation | Sanity check against the ideal ordering |

### 5.4 Hyperparameters

A small documented grid over `num_leaves`, `learning_rate`, `min_data_in_leaf`,
`feature_fraction` and `lambdarank_truncation_level`. Selection is by validation NDCG@10 with
early stopping. The grid stays small: with roughly 200 query groups, an extensive search
would overfit the validation set.

### 5.5 Baseline

`ranking/baseline.py` implements a rule-based scorer in about twenty lines: certification
overlap, plus a bonus for clearing the experience threshold, plus a shift-match bonus.

This is **not a competing model**. It is a measuring stick. Without it, an NDCG of 0.82 is an
uninterpretable number.

If LambdaRank cannot beat this baseline by a meaningful margin, the honest conclusion is that
machine learning added nothing to this problem, and that conclusion goes into the model card.
A project that reports this outcome truthfully is more trustworthy than one that quietly omits
the comparison.

### 5.6 Score semantics

A LambdaRank output is an **uncalibrated relative score**. It is not a probability.

It is not valid to say "this candidate has an 87% chance of being hired". It is only valid to
say "this candidate ranks above that one for this posting". Scores are not comparable across
different postings.

The API returns ranks as the primary field, with raw scores marked as relative. The
explainability documentation repeats this point, because misreading a ranking score as a
probability is the most likely way for this system to be misused.

---

## 6. Explainability

### 6.1 Method

SHAP `TreeExplainer` over the trained LightGBM booster, producing exact per-feature
contributions to the raw ranking score.

TreeExplainer is chosen because it is exact for tree ensembles rather than approximate, and
fast enough to run inline in a request.

### 6.2 Local explanations

Every ranked candidate carries the contribution of each feature to their score:

```json
{
  "candidate_id": "c_0412",
  "rank": 1,
  "score": 2.84,
  "score_type": "relative_ranking_score",
  "explanation": {
    "base_value": 0.51,
    "contributions": [
      {"feature": "licence_match",      "value": 1,    "contribution":  0.94},
      {"feature": "cert_overlap_ratio", "value": 0.75, "contribution":  0.61},
      {"feature": "exp_gap",            "value": 2.0,  "contribution":  0.48},
      {"feature": "shift_match",        "value": 1,    "contribution":  0.37},
      {"feature": "recency_months",     "value": 14,   "contribution": -0.07}
    ]
  },
  "reasons": [
    "Holds the required security licence",
    "Holds 3 of 4 required certifications",
    "2 years above the minimum experience requirement",
    "Available for the required night shift pattern"
  ]
}
```

Two layers are returned deliberately. `contributions` is the auditable numeric record.
`reasons` is the human-readable rendering produced by `explain/reasons.py`, which maps
features and their signs onto plain-language statements. HR reads the second; an auditor
reads the first.

### 6.3 Global explanations

Aggregate SHAP importance across the evaluation set is published in the model card, so it is
visible which features drive the model overall — and so that an unexpectedly influential
feature can be caught during review rather than in production.

### 6.4 Interpretation caveat

SHAP contributions here are additive with respect to the **raw ranking score**, not to a
probability. A contribution of +0.94 does not mean "94% more likely to be hired"; it means
that feature pushed the candidate up the ordering by that much on the model's internal scale.
This warning is carried in `docs/explainability.md` and in the API response schema
documentation.

---

## 7. Bias and Fairness

### 7.1 Three-layer defence

**Layer one — prevention.** Protected attributes are architecturally unreachable from the
feature builder (Sections 2.6 and 4.2).

**Layer two — proxy monitoring.** The proxy register (Section 4.3) tracks features that leak
protected information indirectly.

**Layer three — measurement.** Outcomes are measured by group, and thresholds are enforced in
CI.

### 7.2 Metrics

Standard classification fairness metrics are insufficient here, because this system produces
a ranking. Being placed eleventh instead of second is a real harm even when both candidates
are technically "in the list". The audit therefore measures both selection and position.

| Metric | Definition | Threshold |
|---|---|---|
| Adverse impact ratio | Lowest group's top-k selection rate over the highest group's | ≥ 0.80 (four-fifths rule) |
| Demographic parity gap | Largest difference in top-k selection rate between groups | ≤ 0.10 |
| Equal opportunity gap | Among genuinely qualified candidates, largest difference in top-k rate | ≤ 0.10 |
| Exposure ratio | Group's mean position-discounted exposure, normalised | ≥ 0.80 |

Exposure is the ranking-specific metric. Given a standard position discount of
`1 / log2(rank + 1)`, it captures the fact that rank 1 delivers far more benefit than rank 10,
and detects a model that admits a group into the shortlist but consistently places them lower
within it.

The 0.80 threshold on adverse impact follows the four-fifths rule, a long-standing benchmark
in employment discrimination assessment.

**k is fixed at 10** for every top-k metric above, matching the intended reviewer shortlist
depth. It is defined once in configuration (`FAIRNESS_TOP_K`) and consumed by the audit, the
tests and the model card, so a single change propagates everywhere and the reported numbers
always describe the shortlist that reviewers actually see.

### 7.3 Audit and enforcement

`fairness/audit.py` runs the full metric suite against the held-out set and writes
`fairness.json` into the model's version directory. Every model artifact therefore ships with
its own fairness record.

`tests/test_fairness.py` fails the build when any threshold is breached. This is a hard CI
gate.

Both this gate and the leakage gate will be deliberately broken during development to confirm
they actually fail. An untested gate provides false assurance, which is worse than no gate.

### 7.4 If a threshold is breached

Options, in order of preference:

1. Investigate the responsible feature via SHAP and remove or bucket it.
2. Reweight training examples to balance group representation.
3. Apply post-processing re-ranking to equalise exposure.
4. Escalate to human review, and document the model as unfit for automated shortlisting.

Passing a fairness gate by loosening the threshold is not an option.

### 7.5 Boundaries of this analysis

This audit is performed on synthetic data with synthetic demographics. It demonstrates that
the machinery works; it does **not** certify that the model is fair on SAJCO's real applicant
population. Before any production use, the audit must be re-run against real held-out data
and reviewed by someone with employment-law expertise for the relevant jurisdiction.

---

## 8. Serving

### 8.1 Endpoints

Eleven, and they are grouped here by **what they depend on** rather than by subject, because
that is the distinction a caller has to act on.

| Method | Path | Purpose | Needs a verified model |
|---|---|---|---|
| POST | `/rank` | Primary — many candidates against one job, ranked with explanations | Yes |
| POST | `/score` | One candidate against one job | Yes |
| POST | `/parse` | CV text to structured profile; useful for debugging extraction | Yes |
| POST | `/extract` | Text out of one uploaded PDF, Word or plain-text document | No |
| GET | `/sample-candidates` | Generated applications, for exercising the ranking at volume | No |
| GET | `/fairness` | The audit the loaded artifact carries | Yes |
| GET | `/feature-importance` | What the ranking rests on, over a fixed sample | Yes |
| GET | `/health` | Liveness | No |
| GET | `/ready` | Readiness — model loaded and checksums verified | Answers either way |
| GET | `/model-info` | Active model version and metadata | Yes |
| GET | `/metrics` | Prometheus exposition | No |

The four routes added after this document was first written are not incidental. `/extract` and
`/sample-candidates` exist because the brief opens with *"Given SAJCO's hiring volume"* and the
first interface required every CV to be pasted by hand, which is fine for three and useless for
three hundred. Neither touches the model, so both answer while it is still verifying — a caller
can prepare a batch before the service is able to score it.

`/fairness` and `/feature-importance` exist because the fairness machinery in section 7 and the
global importance in section 6.3 were enforced in CI and readable nowhere. They report what the
loaded artifact already carries and compute no new claim about it, which is why the registry
reaches them by configuration rather than on the request path.

### 8.2 Design points

The model is loaded once during the FastAPI lifespan startup, not per request. If artifacts
are missing or a checksum fails, startup fails loudly rather than serving a degraded service.

`/rank` accepts at most 500 candidates per request. Unbounded batch sizes are an availability
risk.

Every request carries a `request_id`, propagated into logs and returned in the response, so a
specific ranking decision can be reconstructed later from the logs.

Request and response bodies are validated by Pydantic. Malformed input is rejected at the
boundary with a clear error rather than reaching the feature builder.

### 8.3 The interface, and the trust boundary it preserves

Added in Phase 15, after the reversal recorded in the appendix. A Next.js workspace serves the
ranking flow: the posting form, the applications, and the ranked shortlist with its explanations.

**The browser never calls this service.** Every request goes to a route handler inside the
Next.js server, which makes the onward call itself:

```
browser --> /api/rank  (Next.js, same origin) --> FastAPI /rank
```

That is a decision about the trust boundary rather than about convenience. The alternative was
`CORSMiddleware` on this service, which means maintaining a list of every origin permitted to
reach a hiring model, and a wrong list fails silently: access widens while nothing appears
broken. The proxy removes the question instead of answering it, and this service therefore keeps
the boundary it was reviewed with. There is no CORS configuration anywhere in the repository.

The handler carries an endpoint allowlist rather than forwarding whatever it is handed. Without
one it is an open relay to everything in 8.1 from any page able to reach it, `/metrics` included.
It forwards status and body unchanged, because a proxy that flattened a `503` into a `500` would
destroy the distinction between "wait and retry" and "fix your input".

A server-side integration -- an HR system, a script, a scheduled job -- remains a supported
caller and reaches 8.1 directly. Only the browser is routed.

### 8.4 What the interface refuses to render

Three constraints are enforced in the client for reasons that come from this design rather than
from visual preference. They are the interface's share of the honesty argued for elsewhere in
this document:

- **The score is never shown as a proportion.** No percentages, rings or progress bars. Section 5
  establishes that a LambdaRank output is an ordering within one posting; every one of those
  idioms implies a quantity it does not carry, and a reviewer reads a filled ring as "83 per cent
  suitable" regardless of the caption beneath it.
- **A missing value is never shown as zero.** Section 3 establishes that the parser records an
  unstated fact as `None` and refuses to infer a negative from silence. The interface renders
  "not stated", because collapsing the two would reintroduce exactly that inference.
- **The disclaimer is rendered from the response body**, never from a copy held client-side, so
  the constraint cannot drift from the service that issues it.

Full detail in [frontend.md](frontend.md).

---

## 9. Model Versioning and Artifacts

### 9.1 What is wrong with a bare pickle

A loose `model.pkl` has no record of when it was trained, on what data, with which code, or
how it performed. It cannot be rolled back with confidence, and unpickling arbitrary files is
a security risk.

### 9.2 The artifact contract

```
models/v0.1.0/
├── model.txt              LightGBM native text format (not pickle)
├── feature_names.json     Canonical feature names and order
├── metadata.json          Train date, data version, seed, git SHA, library versions
├── metrics.json           NDCG, MAP, MRR, and baseline comparison
├── fairness.json          Full fairness audit output
└── checksums.json         SHA-256 of every artifact in this directory
```

LightGBM's native text format is used instead of pickle: it is human-readable, portable
across library versions, and carries no arbitrary-code-execution risk.

### 9.3 Selection and rollback

The active version is chosen by the `MODEL_VERSION` environment variable. Rollback is a
configuration change, not a rebuild.

At startup the service verifies checksums and confirms that `feature_names.json` matches the
feature registry in code. Any mismatch aborts startup.

### 9.4 Versioning scheme

Semantic versioning. Major for a breaking feature-contract change, minor for retraining with
new data or features, patch for a fix that leaves the contract intact.

---

## 10. Logging and Monitoring

### 10.1 Logging

`structlog` emitting JSON. No `print()` anywhere in the codebase; a lint rule enforces this.

Every log line carries `request_id`, `model_version`, and a timestamp.

**What is never logged:** raw CV text, candidate names, and any protected attribute. Logs are
retained and widely readable, so treating them as a PII sink is a real risk. Logging is
restricted to identifiers, derived numeric features, and outcomes.

### 10.2 Metrics

Prometheus, exposed at `/metrics`:

- Request count and latency histogram, by endpoint and status
- Parse failure rate and parse warning rate
- Score distribution summary
- Candidates-per-rank-request histogram
- Active model version, as a labelled gauge

### 10.3 Drift hook

`core/metrics.py` records a periodic snapshot of input feature distributions. Formal drift
detection is out of scope for this iteration, but capturing the baseline now is what makes it
possible later. A model that was fair and accurate at training time can become neither as the
applicant population shifts.

---

## 11. Testing and CI

### 11.1 Test layers

| Test file | Covers |
|---|---|
| `test_parsing.py` | Phrasing variants, typos, missing fields, ambiguity |
| `test_features.py` | Feature correctness, ranges, missing-value handling |
| `test_leakage.py` | **Gate** — protected attribute reaching features fails the build |
| `test_ranking.py` | Group construction, split integrity, baseline comparison |
| `test_explain.py` | Contributions sum to the score, reason mapping |
| `test_fairness.py` | **Gate** — threshold breach fails the build |
| `test_api.py` | Contract, validation, error handling, batch limits |
| `test_registry.py` | Checksums, feature contract, immutability, **artifact bytes are LF on every platform** |
| `frontend/src/lib/*.test.ts` | Both `422` body shapes, `503` retryability, the additivity check, and that a rejected CV cannot reach an error message |

The two gates are the tests that make this project production-ready rather than merely
functional. They are the mechanism by which a fairness regression becomes a build failure
instead of a discovery made months later.

### 11.2 Pipeline

GitHub Actions on every push and pull request:

```
lint      ruff + mypy
tests     pytest with coverage, threshold enforced
gates     pytest -m gate, as its own job
frontend  eslint + tsc + vitest + next build
docker    both images built, both started, both checked non-root
```

The gates run as their own job as well as inside the full suite, so the checks list answers "did
the fairness gate pass" directly rather than by inference.

The Docker build runs in CI from the start. GitHub runners provide Docker, so the image is
validated before Docker is installed on the development machine.

**A caution recorded here because it is a CI design point rather than an anecdote.** A pipeline
is worth only what the person reading it does with the result. This one ran red for eleven days
over two real defects -- a test asserting a false premise about the working tree, and artifact
checksums recorded over Windows line endings -- while every local run stayed green. The
machinery worked exactly as designed. The missing step was the one that reads the outcome, and
it was a step in the plan that had never been completed. Section 13 carries the generalised
form.

---

## 12. Deployment

Multi-stage Dockerfile: a build stage installing dependencies and the spaCy model, and a slim
runtime stage carrying only what is needed to serve.

The container runs as a non-root user. Model artifacts are baked into the image so that a
running container is fully self-describing. `docker-compose.yml` provides the local run.

The health and readiness endpoints are wired to container health checks, so an orchestrator
does not route traffic to an instance whose model failed to load.

**Two images since Phase 15**, built from two contexts -- `backend/` and `frontend/` -- so
neither can grow by picking up the other half of the repository. Both run as uid 1001 on a
read-only root filesystem with `no-new-privileges`: the same posture on both sides, because a
stack is only as constrained as its least constrained container. The web service waits on the
API's `/ready` rather than on its process starting, so a reviewer never arrives at a workspace
whose backend cannot answer.

---

## 13. Risks and Open Questions

| Risk | Severity | Mitigation |
|---|---|---|
| **Synthetic-to-real gap** — patterns learned may not transfer to real applicants | High | Stated prominently in the model card; real-data validation required before production use |
| **Circularity** — model relearns the label generator | High | Four mitigations in Section 2.4; NDCG > 0.95 treated as a defect |
| **Proxy discrimination** — a neutral feature carries protected information | High | Proxy register, exposure metrics, CI gate |
| **Score misread as probability** | Medium | Named `relative_ranking_score` in the API; repeated in docs and model card |
| **Parser gaps** — unseen phrasing silently drops a qualification | Medium | Parse warnings surfaced in responses; failure rate tracked as a metric |
| **Cold start** — new job types absent from training data | Medium | Documented limitation; baseline scorer as fallback |
| **Small group sizes** — fairness metrics unstable on small demographic groups | Medium | Report confidence intervals; suppress metrics below a minimum group size |
| **Platform-dependent artifact bytes** — a checksum taken over CRLF verifies the machine that wrote the file rather than the artifact | High — **materialised, see below** | Artifacts written with LF on every platform; `.gitattributes` marks `backend/models/**` as `-text`; two tests assert no artifact file contains CRLF |

### The artifact integrity risk that materialised

This one is listed as materialised rather than mitigated because it happened, and the way it
happened is the part worth keeping.

`v0.1.0` was written on Windows. Python's `write_text` and LightGBM's serialiser both emit the
platform line ending, so the recorded SHA-256 values described bytes containing CRLF. Git, with
`core.autocrlf` set and no `.gitattributes`, normalised those to LF on the way into the
repository. The committed bytes therefore hashed differently from the recorded checksums, and
since verification is not optional and startup re-raises on failure, **the released artifact
would not load on any Linux checkout** — CI, the container, or a contributor not on Windows.

Two things let it survive undetected. It passed on the machine that produced the bytes, so
local runs were always green. And the one step whose purpose was to confirm CI green had never
been completed, so the red pipeline was never read. The process gap and the defect concealed
each other; either one alone would have been caught.

The lesson generalises past line endings: **a verification step that only ever runs in the
environment that produced the thing being verified is not a verification step.** Every integrity
claim in this project is now exercised in a Linux container as well as locally.

Corrected rather than reissued, and only after proving the two byte variants were the same
model — 78 trees, 12 features, bit-identical predictions across 2,000 inputs. Re-recording a
hash against a canonical form is a correction to a record; bumping the version would have
implied a retrain that did not happen and orphaned the metrics already reported for v0.1.0.

### Resolved decisions

These three questions were raised during design review and settled as follows.

**1. Fairness threshold basis — keep the four-fifths rule.** The 0.80 adverse impact
threshold is retained. It originates in US employment law rather than Saudi regulation, but
it is a widely recognised and conservative benchmark, and no stricter local standard was
identified. The threshold is a configuration value, so it can be tightened later without a
code change. Confirming the applicable local standard remains advisable before production
use.

**2. Shortlist depth — k = 10.** All top-k fairness metrics are computed at k = 10, matching
the intended reviewer shortlist size. This is set once in configuration and used by the audit,
the tests and the reported metrics, so the number that appears in the fairness report is the
number that reflects real reviewer behaviour.

**3. Candidate disclosure — not in scope for this system.** Candidates will not be notified
that automated ranking is used. This is a business and compliance decision rather than a
technical one, and it sits outside what this service controls; the system produces rankings
and explanations, and any candidate-facing communication is handled elsewhere. The
explanations this system stores mean that a per-candidate rationale can be produced on request
if that position changes. Whoever owns hiring compliance should confirm this against local
disclosure requirements.

---

## 14. Implementation Plan

| Phase | Content |
|---|---|
| 0 | Design doc, architecture diagrams |
| 1 | Repo setup, environment, tracking files, first push |
| 2 | Core infrastructure — config, logging, metrics, schemas |
| 3 | Synthetic data generator with anti-circularity design |
| 4 | Parser |
| 5 | Features, blocklist, leakage gate |
| 6 | Baseline and LambdaRank model |
| 7 | Model registry |
| 8 | SHAP explainability |
| 9 | Fairness audit and report |
| 10 | FastAPI service |
| 11 | Tests, Dockerfile, CI |
| 12 | Local Docker verification |
| 13 | Model card, README, release tag |

Dependencies are strictly sequential from Phase 3 onward, with one exception: the fairness
metric implementations (9.1) depend only on the data generator and can be written in parallel
with the model work.

### 14.1 Phases added after this plan was written

Phases 0-13 delivered the brief as written. **Fifteen more followed.** They are listed here
rather than left out, so this document describes the project that exists rather than the one that
was predicted — including the two that were built and undone, which are the most informative rows
in the table.

| Phase | Content | Why it was not in the original plan |
|---|---|---|
| 14 | Split into `backend/` and `frontend/` | A single runtime needed no split |
| 15 | Rank workspace frontend | A frontend was a locked decision against — reversed, see the appendix |
| 16 | The frontend written into every document | Five documents described a system that stopped at the API, because when they were written it did |
| 17 | Frontend redesign, re-measured for WCAG AA on every surface | The first pass was correct and plain; the constraints it enforces were the valuable part and did not change |
| 18 | Flow verification and cleanup | Running the documented quick start found a command in it that could never succeed |
| **19** | **Violet palette — built, measured, and reverted** | Requested, delivered with thirty pairs measured, then judged worse than the teal it replaced. The person who looks at it every day is the one who gets to say so |
| 20 | Volume, and upload that needs no backend | The brief's premise was hiring volume and the interface required pasting. A bulk path already worked end to end; volume was a missing button rather than a missing capability |
| **21—22** | **Fairness dashboard and provenance page — built, then removed** | Both rendered real endpoints faithfully and both were aimed at the wrong reader: a recruiter working a shortlist does not consult an adverse impact ratio. **The endpoints were kept**; what was removed is the browser's ability to reach them |
| 23 | PDF and DOCX upload | A scanned PDF has no text layer, extracts to nothing, and would rank last — a candidate placed at the bottom because their file could not be read. Refused at upload instead, and OCR rejected for reproducing the same failure in a new form |
| 24 | Filter, sort and CSV export | Filtering never renumbers a rank, and the export carries the disclaimer as its first row |
| 25 | UI hierarchy and rhythm | Refinement, and the user's verdict was that nothing had changed. That verdict was correct: refinement is not redesign |
| 26 | Console — a new visual language | Flat surfaces, dense rows, micro labels. Changed what the design *is* rather than how well it works |
| 27 | The workspace, from a supplied mockup | Light, soft and elevated, with a sidebar rail and statistic tiles. Two things in the mockup could not be built and were refused rather than approximated — see the appendix |
| 28 | Final audit: structure, and every document current | The frontend arrived at Phase 15 and the documents predating it had been patched eleven times rather than rewritten |

Phases 16 and 28 exist because of a failure mode worth naming twice. The interface was built,
and the documents describing the system were not revisited. Each one remained internally consistent
and collectively they were wrong: this section, section 8 and section 12 all described a system with
no browser in it. **A component added late does not announce itself in the diagrams that predate
it**, and nothing in a test suite fails when a document goes stale.

---

## 15. Appendix

### 15.1 Dependencies

| Package | Purpose |
|---|---|
| `fastapi`, `uvicorn` | API service |
| `pydantic`, `pydantic-settings` | Schemas and configuration |
| `spacy` + `en_core_web_sm` | NLP pipeline |
| `rapidfuzz` | Fuzzy certification matching |
| `lightgbm` | LambdaRank ranker |
| `shap` | Explainability |
| `scikit-learn` | Metrics and splitting utilities |
| `pandas`, `numpy` | Data handling |
| `faker` | Synthetic data generation |
| `structlog` | JSON logging |
| `prometheus-client` | Metrics exposition |
| `pytest`, `pytest-cov`, `httpx` | Testing |
| `ruff`, `mypy` | Linting and type checking |

Python 3.12, in a dedicated conda environment.

### 15.2 Design decisions rejected, and why

| Considered | Rejected because |
|---|---|
| Sentence embeddings for matching | 500 MB of weight, and similarity scores are not auditable in a hiring context |
| LLM-based CV parsing | Non-deterministic, costly, no traceable audit path |
| Binary classifier instead of LambdaRank | The task is ranking; graded relevance carries more signal than a hire/no-hire flag |
| Pickle for model storage | No provenance, version-fragile, arbitrary code execution risk |
| Real or scraped CV data | PII, no labels, and inherited historical bias |
| A frontend | Not requested in the brief; Swagger UI is sufficient for demonstration — **reversed 2026-08-19, see below** |
| A **match level** on each candidate ("Strong / Moderate / Weak") | The training labels are graded 0-3, so a level is meaningful in the label space, but the output has no calibration to those grades. Any level shown would be a threshold the interface invented, and section 5.6 is explicit that nothing in the output supports one. Replaced with a count of the posting's own stated requirements, where an unstated value never counts as a failure |
| A **score out of 100** | The model emits a relative ranking score within one posting. `/100` reads as "92% suitable" whatever caption sits beside it, which is the exact failure section 8.4 exists to prevent |
| **OCR** for scanned PDFs | A large dependency whose failure mode is the one this project exists to prevent: mis-read text ranks confidently and wrongly, with nothing signalling it. A CV whose certifications were garbled scores like one that could not be read at all, except now nothing marks it. Refused at upload instead |
| Medals or a trophy on the top-ranked candidates | A reward metaphor. A medal says a person won something; the only available claim is that one CV matched a posting's stated requirements more closely than another. The rank number carries the ordering without the framing |
| A different avatar colour per candidate | The palette reserves colour for meaning — amber is a constraint on use, positive and negative are the direction of a contribution. An orange avatar would read as a warning about that person and a green one as something in their favour, neither of which is being claimed |
| A shareable link to a ranking | It turns a working file into a record of a decision, which is the same argument that keeps a shortlist unpersisted |
| Per-certification ticks in the breakdown | `POST /rank` returns `cert_overlap_count`, not which certifications matched. Naming them individually would need a second parse request per candidate, so the count is shown, since the count is what the model used |
| Elevation for the leading candidate | Depth is not available in every rendering. The border carries it instead, which survives a screenshot, a print, and a viewer who cannot separate two shadows |

**On the frontend reversal.** The original reasoning was sound for the brief as written, and
it is left in the table above rather than edited away. What changed is not the brief but an
observation about this system in particular: its most distinctive output is a per-candidate
explanation that reconstructs the score it explains, and a reviewer who is not reading JSON
cannot see that at all. Swagger UI demonstrates that the endpoint answers; it does not
demonstrate what the answer is for. A shortlisting aid whose explanations are unreadable by
the person doing the shortlisting is only half-delivered.

The reversal is deliberately narrow. One workspace for the ranking flow was added; the
service contract, the model and the fairness machinery are untouched, and the browser never
speaks to the API directly, so the audited service keeps the trust boundary it was reviewed
with.

**On the refusals.** Five of the rows above were added at Phase 27, when a design mockup was
supplied and asked for. Most of it was built. Two things in it — a score out of one hundred and a
"Strong match" badge — assert a calibration this model does not have, and both were resolved by
**keeping the shape and changing the claim**: the same large figure in the same position carrying
the real score, and the same badge carrying a counted fact.

That distinction is the one worth carrying forward. A request for a design is not a request for the
claims a design happens to imply, and the useful answer to "make it look like this" is usually the
layout with the assertion removed rather than either the layout or the assertion alone.

---

**End of design document.** Implementation begins only after review and approval of this
document.
