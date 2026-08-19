# GuardMatch AI

Ranks security guard applicants against a job posting's requirements — certifications,
experience, availability — and explains why each candidate landed where they did.

[![CI](https://github.com/Kainatfatima0311/guardmatch-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/Kainatfatima0311/guardmatch-ai/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.12-blue)
![Coverage](https://img.shields.io/badge/coverage-95%25-brightgreen)
![Licence](https://img.shields.io/badge/licence-MIT-lightgrey)


## The problem

A single guard vacancy at SAJCO can attract several hundred applications. Every one has to be
checked against the same requirements: a valid security licence, minimum experience, specific
certifications, availability for the shift the site actually needs.

Done by hand this costs days, produces different answers from different reviewers, and leaves
no record of the reasoning. When a candidate asks why they were not shortlisted, there is
nothing to point at.

GuardMatch parses each application, compares it against the posting, and returns a ranked
shortlist where every placement comes with an explanation.

**It is a shortlisting aid.** It orders a queue for a human reviewer. It does not reject
candidates and does not make hiring decisions.

## How it works

```
CV text ──▶ Parser ──▶ Features ──▶ LambdaRank ──▶ SHAP ──▶ ranked list
            spaCy      pairwise      LightGBM      exact     + reasons
            + regex    12 features                 contributions
                          │
                          └── protected attributes cannot reach here
```

| Concern | Choice | Why |
|---|---|---|
| Extraction | spaCy `EntityRuler` + regex + `rapidfuzz` | Deterministic and auditable. A match traces to a named pattern; a similarity score does not |
| Ranking | LightGBM `lambdarank`, graded relevance 0–3 | Ranking is a set problem — who is best *for this posting*, not who is best in general |
| Explanations | SHAP `TreeExplainer` | Exact for tree ensembles, and additive: contributions reconstruct the score |
| Fairness | Blocked at the type level, proxies monitored, outcomes audited in CI | Prevention cannot see proxies; measurement only catches harm after it is learned |
| Serving | FastAPI, checksum-verified versioned artifacts | A model that cannot verify itself should not answer questions |
| Data | Synthetic and seeded | No real CVs, no PII, fully reproducible |

## Results

Measured on 50 held-out postings, split at the posting level.

| Metric | Rule-based baseline | LambdaRank |
|---|---|---|
| NDCG@10 | 0.804 | **0.904** (+12.4%) |
| MAP | 0.804 | 0.899 |

The baseline is a twenty-line rule with no learned parameters. It is here because 0.904 means
nothing on its own — the comparison is what shows machine learning earned its place.

**The measured score exceeds the 0.75–0.85 band the design doc predicted.** The target was not
adjusted afterwards. The honest reading is that the synthetic task is easier than real hiring,
and that is recorded as a limitation rather than presented as performance.

Fairness audit at k = 10 passes on gender, age band and nationality — with the important
caveat that the four-fifths rule missed a realistically-sized proxy bias during testing. See
[the fairness report](docs/fairness-report.md).

## Quick start

Requires Python 3.12.

```bash
cd backend
conda create -n guardmatch python=3.12 -y
conda activate guardmatch
pip install -e ".[dev]"
python -m spacy download en_core_web_sm
```

Generate data, train, audit, serve — all from `backend/`:

```bash
guardmatch generate-data --seed 42
guardmatch train --version v0.1.0
guardmatch audit --version v0.1.0
uvicorn guardmatch.api.app:app --reload
```

Then open <http://localhost:8000/docs>.

A trained `backend/models/v0.1.0/` is committed, so the API runs without training anything.

### The workspace

Requires Node 22. In a second terminal, with the API already running:

```bash
cd frontend
npm ci
npm run dev
```

Then open <http://localhost:3000>, press **Load samples** and rank them. Expanding a
candidate shows all twelve feature contributions and checks, in the browser, that they add
back up to the score.

The browser never calls the API directly — requests go through a route handler in the
Next.js server. That is why there is no CORS configuration anywhere in the backend: there is
no cross-origin request to permit. See [the frontend notes](docs/frontend.md).

### Docker

From the repository root:

```bash
docker compose up --build
```

<http://localhost:3000> for the workspace, <http://localhost:8000/docs> for the API.

| Image | Size | Built from |
|---|---|---|
| `guardmatch-ai` | 1.37 GB | `backend/` |
| `guardmatch-web` | 325 MB | `frontend/` |

Two build contexts rather than one, so neither image can grow by picking up the other half
of the repository. Both run as uid 1001 on a read-only root filesystem with
`no-new-privileges`; the API bakes its model artifacts in rather than mounting them, so a
running container fully describes the model it serves. `web` waits on the API's `/ready`
health check, not merely on its process starting.

### Task runner

`make` on Linux and macOS, `tasks.ps1` on Windows — same targets either way.

```bash
make help      # list targets
make check     # lint, typecheck, test — everything CI runs
make gates     # fairness and leakage gates only
```

```powershell
.\tasks.ps1 check
```

## Using the API

```bash
curl -X POST http://localhost:8000/rank \
  -H 'Content-Type: application/json' \
  -d '{
    "job": {
      "job_id": "j_1",
      "required_certifications": ["security_licence", "fire_safety"],
      "min_years_experience": 4.0,
      "shift_pattern": "night",
      "site_type": "construction",
      "driving_required": true
    },
    "candidates": [
      {"candidate_id": "c_1", "cv_text": "PROFILE\nGuard with 6 years of experience.\n\nCERTIFICATIONS\n- SIA licence\n- fire marshal"}
    ]
  }'
```

Every ranked candidate comes back with the numbers and the words:

```json
{
  "candidate_id": "c_1",
  "rank": 1,
  "relative_ranking_score": 2.9705,
  "score_type": "relative_ranking_score",
  "explanation": {
    "base_value": -2.0226,
    "contributions": [
      {"feature": "shift_match", "value": 1.0, "contribution": 0.9412},
      {"feature": "licence_match", "value": 1.0, "contribution": 0.5511}
    ],
    "reasons": [
      "Available for the shift pattern this role needs — counted moderately in favour",
      "Holds the required security licence — counted moderately in favour"
    ]
  }
}
```

> **Scores are not probabilities.** A LambdaRank output is meaningful only as an ordering
> within one posting. It is not comparable across postings and does not express a likelihood
> of being hired. Every `/rank` response carries this constraint in a `disclaimer` field, so it
> travels with the data rather than living only in documentation.

| Endpoint | Purpose |
|---|---|
| `POST /rank` | Rank candidates for one job — the primary endpoint |
| `POST /score` | Score one candidate (returns no rank — 1-of-1 is not a comparison) |
| `POST /parse` | Extract structured facts from CV text |
| `GET /health` `/ready` | Liveness and readiness — deliberately different questions |
| `GET /model-info` `/metrics` | Provenance and Prometheus exposition |

Full detail in the [API reference](docs/api-reference.md).

## Fairness

Three layers, deliberately redundant.

**Prevention.** `ParsedProfile` — the type the whole pipeline is built on — has no name, no
age, no gender, no demographic field of any kind. They are not filtered out later; they are
absent from the start. A static test fails the build if any module on the scoring path imports
the module where demographics live.

The point: using a protected attribute must require *adding* an import that does not exist,
not *forgetting* a filter that does. An addition shows up in code review.

**Proxy monitoring.** Four permitted features can carry demographic information indirectly.
Each is registered with its mitigation. `shift_match` is the known worst case — it is also the
model's single largest input at 26.8%.

**Measurement.** Adverse impact, demographic parity, equal opportunity, and an
exposure-weighted metric that catches a group being admitted to the shortlist but placed
consistently lower within it. Enforced in CI.

Both gates are proven to fail, not merely assumed to work:

```bash
pytest -m gate -v
```

A gate that has never failed proves nothing about what it claims to detect.

## Documentation

| Document | Contents |
|---|---|
| [Design doc](docs/design-doc.md) | Full design, decisions rejected, risks |
| [Architecture](docs/architecture.md) | Component, request-flow and trust-boundary diagrams |
| [Model card](docs/model-card.md) | Intended use, out-of-scope uses, limitations, conditions of use |
| [Fairness report](docs/fairness-report.md) | Metrics, what the audit caught, and what it missed |
| [Explainability](docs/explainability.md) | Method, worked examples, global importance |
| [Data card](docs/data-card.md) | Generation, anti-circularity design, bias injection |
| [API reference](docs/api-reference.md) | Endpoints, schemas, errors |
| [Frontend](docs/frontend.md) | Colour system with measured contrast, the constraints enforced in code, what was not built |

## Project layout

```
guardmatch-ai/
├── backend/                 the service and the pipeline behind it
│   ├── src/guardmatch/
│   │   ├── core/            config, structured logging, metrics
│   │   ├── schemas/         Pydantic contracts and closed vocabularies
│   │   ├── data/            synthetic generator (protected attributes held separately)
│   │   ├── parsing/         spaCy + regex extraction
│   │   ├── features/        pairwise features + protected attribute blocklist
│   │   ├── ranking/         baseline, LambdaRank, evaluation
│   │   ├── explain/         SHAP contributions and plain-language reasons
│   │   ├── fairness/        metrics and audit
│   │   ├── registry/        versioned, checksummed artifacts
│   │   └── api/             FastAPI service
│   ├── tests/               337 tests
│   ├── models/v0.1.0/       committed artifacts, six files, all checksummed
│   └── data/                generated from a seed, not committed
├── docs/                    the documents below
├── docker-compose.yml
├── Makefile · tasks.ps1     one task list for the whole repository
└── .github/workflows/
```

`docs/` sits at the root rather than inside `backend/` because those documents describe the
project — its design, its fairness position, its limitations — not one runtime within it.

Paths quoted inside `docs/architecture.md` diagrams are relative to `backend/`.

## Testing

```bash
cd backend
pytest              # 337 tests, 95% coverage, threshold enforced at 85%
pytest -m gate      # fairness and leakage gates only
pytest -m "not slow"
```

CI runs lint, type checking, the full suite, the gates as a separate job, and a Docker build
that starts the container and verifies it serves a checksum-verified model as a non-root user.

## Limitations

Read the [model card](docs/model-card.md) before drawing conclusions from any number here. The
short version:

- **Trained on synthetic data.** Real-world performance is unknown.
- **The fairness audit missed a realistically-sized proxy bias** during testing. Passing the
  four-fifths rule is not evidence of fairness.
- **Scores are not probabilities** and are not comparable across postings.
- **Human review is a condition of use**, not a recommendation.

## Licence

MIT
