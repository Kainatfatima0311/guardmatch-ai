# GuardMatch AI

Resume screening and guard job matching. Ranks security guard applicants against a job
posting's requirements — certifications, experience, availability — and explains why each
candidate landed where they did.

> **Status: in development.** The design is complete and the project skeleton is in place;
> the pipeline is being built phase by phase. This README is expanded into full setup and
> usage documentation once the service runs end to end.

## What it does

A single guard vacancy at SAJCO can attract hundreds of applications. Screening them by hand
is slow, inconsistent between reviewers, and leaves no record of the reasoning. GuardMatch
parses each application, compares it against the posting, and returns a ranked shortlist with
a per-candidate explanation.

It is a **shortlisting aid**. It orders a queue for a human reviewer — it does not reject
candidates and does not make hiring decisions.

## Approach

| Concern | Choice |
|---|---|
| Extraction | spaCy `EntityRuler` + regex + `rapidfuzz` — deterministic and auditable |
| Ranking | LightGBM `lambdarank` with graded relevance 0–3 |
| Explanations | SHAP `TreeExplainer`, exact per-feature contributions |
| Fairness | Protected attributes architecturally unreachable from features; four-fifths rule enforced in CI at k = 10 |
| Serving | FastAPI, with versioned and checksum-verified model artifacts |
| Data | Synthetic and seeded — no real CVs, no PII |

Two hard CI gates make the fairness work real rather than decorative: a **leakage gate** fails
the build if a protected attribute reaches the feature set, and a **fairness gate** fails it if
adverse impact drops below 0.80.

## Documentation

| Document | Contents |
|---|---|
| [docs/design-doc.md](docs/design-doc.md) | Full design: data strategy, model, fairness, API, risks |
| [docs/architecture.md](docs/architecture.md) | Component, request-flow and trust-boundary diagrams |

Additional documents — data card, explainability write-up, fairness report and model card —
are produced as the corresponding phases complete.

## Development

Requires Python 3.12 (conda recommended).

```bash
conda create -n guardmatch python=3.12 -y
conda activate guardmatch
pip install -e ".[dev]"
python -m spacy download en_core_web_sm
```

Task runner — `make` on Linux and macOS, `tasks.ps1` on Windows:

```bash
make help          # list targets
make check         # lint, typecheck and test — everything CI runs
```

```powershell
.\tasks.ps1 help
.\tasks.ps1 check
```

## Licence

MIT
