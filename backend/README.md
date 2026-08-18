# GuardMatch AI — Backend

The scoring service and the machine learning pipeline behind it: CV parsing, pairwise
feature construction, a LambdaRank ranker, SHAP explanations, the fairness audit, and the
FastAPI service that serves all of it from checksum-verified versioned artifacts.

For what the project is and why it is built this way, see the [root README](../README.md)
and the [design doc](../docs/design-doc.md). This file covers only how to run the backend.

## Layout

```
backend/
├── src/guardmatch/
│   ├── core/       config, structured logging, metrics
│   ├── schemas/    Pydantic contracts and closed vocabularies
│   ├── data/       synthetic generator (protected attributes held separately)
│   ├── parsing/    spaCy + regex extraction
│   ├── features/   pairwise features + protected attribute blocklist
│   ├── ranking/    baseline, LambdaRank, evaluation
│   ├── explain/    SHAP contributions and plain-language reasons
│   ├── fairness/   metrics and audit
│   ├── registry/   versioned, checksummed artifacts
│   ├── api/        FastAPI service
│   └── cli.py      generate-data, train, audit
├── tests/          337 tests, 95% coverage
├── models/v0.1.0/  committed artifacts — six files, all checksummed
├── data/           generated from a seed, not committed
└── notebooks/
```

## Setup

Requires Python 3.12. Every command below is run from this directory.

```bash
conda create -n guardmatch python=3.12 -y
conda activate guardmatch
pip install -e ".[dev]"
python -m spacy download en_core_web_sm
```

## Running

```bash
guardmatch generate-data --seed 42     # writes data/
guardmatch train --version v0.1.0      # writes models/v0.1.0/
guardmatch audit --version v0.1.0      # writes fairness.json into the artifact dir
uvicorn guardmatch.api.app:app --reload
```

A trained `models/v0.1.0/` is committed, so the API runs without training anything.
Interactive docs at <http://localhost:8000/docs>.

There is no `guardmatch serve` command — the CLI covers the pipeline, and the service is
started by an ASGI server, which is the thing that owns host, port and worker count.

## Configuration

Every setting has a default in `src/guardmatch/core/config.py` and is overridable by an
environment variable of the same name in upper case. See [`.env.example`](.env.example) for
the full list. The ones that change behaviour most:

| Variable | Default | Effect |
|---|---|---|
| `MODEL_VERSION` | `v0.1.0` | Which artifact directory to load. Refuses to fall back if absent |
| `MODEL_DIR` | `models` | Artifact root, resolved from the working directory |
| `MAX_RANK_BATCH` | `500` | Candidates accepted in one `/rank` call |
| `LOG_FORMAT` | `json` | `console` is easier to read while developing |

## Tests

```bash
pytest                 # full suite with coverage, threshold enforced at 85%
pytest -m gate -v      # fairness and leakage gates only
pytest -m "not slow"   # fast feedback loop
```

The gates are proven to fail, not merely assumed to work — a gate that has never failed
proves nothing about what it claims to detect.

## Lint and types

```bash
ruff check .
ruff format --check .
mypy src
```

`ruff` bans `print()` across the source tree via the `T20` rule. That is not a style
preference: the brief requires real logging, and banning `print` at lint time is what makes
that requirement enforceable rather than aspirational.

## Container

The image is built from this directory, so the build context contains the source and the
model artifacts but not the frontend.

```bash
docker build -t guardmatch-ai:0.1.0 .
```

From the repository root, `docker compose up --build` starts this service together with the
frontend. Artifacts are baked into the image rather than mounted, so a running container
fully describes the model it serves.

## Task runner

The root [`Makefile`](../Makefile) and [`tasks.ps1`](../tasks.ps1) wrap every command above
and run them in this directory. Prefer them over typing the commands by hand — they are what
CI uses, so a passing `make check` means a passing pipeline.
