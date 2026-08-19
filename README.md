# GuardMatch AI

Ranks security guard applicants against a job posting's requirements — certifications,
experience, availability — and explains why each candidate landed where they did.

Drop a folder of CVs, or generate a couple of hundred to see the volume the problem actually has.
Every placement comes with the twelve numbers behind it, and the interface refuses the things it
cannot read rather than ranking them badly.

[![CI](https://github.com/Kainatfatima0311/guardmatch-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/Kainatfatima0311/guardmatch-ai/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.12-blue)
![Coverage](https://img.shields.io/badge/coverage-94.80%25-brightgreen)
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

End to end, from a dropped CV to a ranked shortlist on screen:

```
 BROWSER                    NEXT.JS                 FASTAPI
 ───────                    ───────                 ───────
 posting + applications
   drop .txt files ─┐
   generate a batch ┼─▶ up to 500 candidates
   paste text ──────┘
      │
      │  validate locally
      │  enums · 20k chars · unique ids · 500 batch
      │  file names held here, never sent
      ▼
 POST /api/rank ──────▶ allowlist check ──────▶ Pydantic, extra="forbid"
   same origin          server-side hop               │
                                                      ▼
                                                   Parser        spaCy + regex + rapidfuzz
                                                      ▼
                                                   Features     12 pairwise
                                                      │         ┌──────────────────────────┐
                                                      │◀────────┤ protected attributes     │
                                                      ▼         │ cannot reach here        │
                                                   LambdaRank   └──────────────────────────┘
                                                      ▼         LightGBM, graded 0–3
                                                    SHAP        exact contributions
                                                      ▼
 ranked list ◀───────── status and body ◀──────── 12 contributions
      │                 unchanged                 + reasons + disclaimer
      │
      │  re-check: base value + 12 contributions = score
      ▼
 rank · reasons · 12 bars · warnings · disclaimer
```

**The browser has no arrow to FastAPI.** Every call goes to a route handler on the Next.js
server, which makes the onward call itself. That is why no CORS configuration exists anywhere in
the backend — there is no cross-origin request to permit.

The last step is the one the interface exists for. SHAP here is additive, so the browser
recomputes `base value + all 12 contributions` and shows whether it reconstructs the score.
Measured deltas run from 0.0e+00 to 1.8e-15.

| Concern | Choice | Why |
|---|---|---|
| Extraction | spaCy `EntityRuler` + regex + `rapidfuzz` | Deterministic and auditable. A match traces to a named pattern; a similarity score does not |
| Ranking | LightGBM `lambdarank`, graded relevance 0–3 | Ranking is a set problem — who is best *for this posting*, not who is best in general |
| Explanations | SHAP `TreeExplainer` | Exact for tree ensembles, and additive: contributions reconstruct the score |
| Fairness | Blocked at the type level, proxies monitored, outcomes audited in CI | Prevention cannot see proxies; measurement only catches harm after it is learned |
| Serving | FastAPI, checksum-verified versioned artifacts | A model that cannot verify itself should not answer questions |
| Data | Synthetic and seeded | No real CVs, no PII, fully reproducible |
| Interface | Next.js, calling the API server-side | The browser never reaches the model, so the audited service keeps the trust boundary it was reviewed with |

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

## Running it

Three ways, fastest first. **A trained `backend/models/v0.1.0/` is committed**, so nothing needs
training to see the system work.

### 1. Everything, one command

Requires Docker.

```bash
docker compose up --build
```

| | |
|---|---|
| <http://localhost:3000> | the Rank workspace — drop CVs or **Generate** a batch, then **Rank applications** |
| <http://localhost:8000/docs> | the API directly, via Swagger UI |

First build takes a few minutes; the API image compiles LightGBM and downloads the spaCy model.
`web` waits for the API's `/ready`, which passes only once the model has loaded *and* its
checksums have verified — so if the workspace comes up, the model it is serving is the one that
was evaluated and audited.

Stop with `docker compose down`.

### 2. Locally, for development

Two terminals. Requires **Python 3.12** and **Node 22**.

**Terminal 1 — the API:**

```bash
cd backend
conda create -n guardmatch python=3.12 -y
conda activate guardmatch
pip install -e ".[dev]"
python -m spacy download en_core_web_sm
uvicorn guardmatch.api.app:app --reload
```

Confirm it came up:

```bash
curl http://localhost:8000/ready
# {"ready":true,"model_version":"v0.1.0","detail":null}
```

If `ready` is `false`, `detail` says why — and the service refuses to serve rather than
answering from a model it could not verify.

**Terminal 2 — the workspace:**

```bash
cd frontend
npm ci
npm run dev
```

Then <http://localhost:3000>. The API is expected on port 8000; point elsewhere with
`BACKEND_URL=http://host:port npm run dev`.

Three ways to get applications in:

- **Drop files.** `.txt`, `.text` and `.md` are read in the browser, so the file itself is never
  uploaded. `.pdf` and `.docx` go to `POST /extract` and come back as text you can read and edit
  before anything is ranked.
- **Generate a batch** — 10 to 250 synthetic applications, which is how to see the hiring volume
  the brief describes. Labelled synthetic everywhere it appears.
- **Paste** — for one or two, or to correct text read from a file.

**A scanned PDF is refused when you drop it, not ranked.** It has no text layer, so it would
extract to nothing, and an empty CV ranks last — the system would place a candidate at the
bottom because their file could not be read, and you would see a weak candidate instead of an
unreadable document. `.doc` and `.rtf` are refused too, naming the conversion. OCR was considered
and rejected: mis-read text produces the same wrong ranking with nothing signalling it.

File names are shown on screen and **never sent**: `name` is a blocked attribute in this system,
so the display name and the request payload are separate types. See
[the frontend notes](docs/frontend.md).

The browser never calls the API directly — requests go to a route handler inside the Next.js
server, which makes the onward call itself. That is why there is no CORS configuration anywhere
in the backend: there is no cross-origin request to permit. See
[the frontend notes](docs/frontend.md).

### 3. Regenerating the data and the model

Only needed to reproduce the artifact from scratch. From `backend/`, with the environment active:

```bash
guardmatch generate-data --seed 42        # writes data/, ~30 s
guardmatch train --version v0.2.0         # a NEW version — see below
guardmatch audit --version v0.2.0         # writes fairness.json into the artifact
```

**Two guards will stop you, and both are deliberate.**

`--version v0.1.0` is refused, because that version already exists and versions are immutable —
overwriting one would leave every metric already reported for `v0.1.0` describing a different
model. Pass a version that is not in use.

Training is also refused from a working tree with uncommitted changes, because the git SHA
recorded in the artifact would describe code that never existed. Commit first, or pass
`--allow-dirty` for a throwaway experiment and accept that the provenance is then a fiction.

Serve a different version with `MODEL_VERSION=v0.2.0 uvicorn guardmatch.api.app:app`. Rollback
is that environment variable, not a rebuild.

### Task runner

`make` on Linux and macOS, `tasks.ps1` on Windows — same targets either way, run from the
repository root, and this is the file CI mirrors.

```bash
make help          # list every target
make check         # lint, typecheck and test both halves — everything CI runs
make gates         # the fairness and leakage gates only
make serve         # the API
make web-dev       # the workspace
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

Ten more endpoints sit beside it. The ones worth knowing:

| | |
|---|---|
| `GET /sample-candidates?count=100` | Generated applications, for exercising the ranking at size |
| `POST /extract` | Text out of one uploaded PDF, Word or plain-text document |
| `GET /fairness` | The audit carried by the loaded model — **three states, not two** |
| `GET /feature-importance` | What the ranking rests on, measured over a fixed sample |
| `GET /ready` | `200` only once the model has loaded *and* its checksums verified |

`/extract` and `/sample-candidates` need no model, so they answer while it is still verifying.
`/fairness` and `/feature-importance` report what the loaded artifact already carries and compute
no new claim about it. Full reference, including both `422` shapes a client has to handle: [API
reference](docs/api-reference.md).

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
consistently lower within it. Enforced in CI, and answerable from the running service at
`GET /fairness` rather than only from a file in the repository.

**A pass is not evidence of fairness.** A
deliberately injected, realistically sized proxy bias **passed at 0.875**; four-fifths is a floor,
not a target. So the page reports three states rather than two — `age_band` sits at **0.627**,
well under the line, and is reported as *cannot tell* rather than as a pass, because after
correcting for ten possible group comparisons it is not distinguishable from noise. Calling that a
pass would be false; calling it a failure would be a claim the data does not support. The
[fairness report](docs/fairness-report.md) is where this is argued rather than asserted.

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
├── backend/                     the service and the pipeline behind it
│   ├── src/guardmatch/
│   │   ├── core/                config, structured logging, metrics
│   │   ├── schemas/             Pydantic contracts and closed vocabularies
│   │   ├── data/                synthetic generator (protected attributes held separately)
│   │   ├── parsing/             spaCy + regex extraction
│   │   ├── features/            pairwise features + protected attribute blocklist
│   │   ├── ranking/             baseline, LambdaRank, evaluation
│   │   ├── explain/             SHAP contributions and plain-language reasons
│   │   ├── fairness/            metrics and audit
│   │   ├── registry/            versioned, checksummed artifacts
│   │   ├── api/                 FastAPI service
│   │   └── cli.py               generate-data · train · audit
│   ├── tests/                   399 tests, 80 of them gates
│   ├── models/v0.1.0/           committed artifacts, six files, all checksummed
│   ├── data/                    generated from a seed, not committed
│   ├── pyproject.toml · Dockerfile · .dockerignore · .env.example
│   └── README.md
├── frontend/                    the Rank workspace
│   ├── src/app/
│   │   ├── page.tsx             intake, shortlist, explanations
│   │   ├── globals.css          design tokens, with measured contrast ratios
│   │   └── api/[...path]/       server-side proxy — why no CORS config exists
│   ├── src/components/          form, results, contribution bars, disclosure
│   ├── src/lib/                 typed contract, file intake, filters, CSV, 69 tests
│   ├── package.json · Dockerfile · .dockerignore
│   └── README.md
├── docs/                        the eight documents below
├── docker-compose.yml           both services, web gated on the API's /ready
├── Makefile · tasks.ps1         one task list for the whole repository
├── .gitattributes               keeps artifact bytes verbatim — see the model card
└── .github/workflows/ci.yml     five jobs
```

`docs/` sits at the root rather than inside `backend/` because those documents describe the
project — its design, its fairness position, its limitations — not one runtime within it.

Paths quoted inside `docs/architecture.md` diagrams are relative to `backend/`.

## Testing

```bash
cd backend
pytest              # 399 tests, 94.80% coverage, threshold enforced at 85%
pytest -m gate      # 80 fairness and leakage gates
pytest -m "not slow"
```

```bash
cd frontend
npm test            # 69 tests: the API contract, file intake, filters, CSV, the proxy
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
