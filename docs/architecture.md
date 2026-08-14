# GuardMatch AI — Architecture

**Companion to:** [design-doc.md](design-doc.md)
**Date:** 2026-08-15

This document holds the structural view of the system: how components fit together, how a
request flows, how the model is trained, and where the boundaries that protect fairness are
drawn.

---

## 1. System Overview

```mermaid
flowchart TB
    subgraph Client
        HR["HR system / reviewer"]
    end

    subgraph API["FastAPI service"]
        MW["Middleware<br/>request_id, timing, logging"]
        RT["Routes<br/>/rank /score /parse /health /metrics"]
    end

    subgraph Pipeline["Scoring pipeline"]
        PARSE["Parser<br/>spaCy + regex + rapidfuzz"]
        FEAT["Feature builder<br/>pairwise features"]
        RANK["Ranker<br/>LightGBM LambdaRank"]
        EXPL["Explainer<br/>SHAP TreeExplainer"]
    end

    subgraph Artifacts["Model registry"]
        REG["models/v0.1.0/<br/>model.txt, feature_names.json,<br/>metadata, metrics, fairness, checksums"]
    end

    subgraph Obs["Observability"]
        LOG["structlog<br/>JSON logs"]
        MET["Prometheus<br/>/metrics"]
    end

    HR -->|"POST /rank"| MW
    MW --> RT
    RT --> PARSE --> FEAT --> RANK --> EXPL
    EXPL -->|"ranked list + reasons"| RT
    RT -->|"JSON response"| HR

    REG -.->|"loaded once at startup"| RANK
    REG -.->|"feature contract check"| FEAT

    MW -.-> LOG
    RT -.-> MET
    PARSE -.-> MET
    RANK -.-> MET
```

Solid arrows carry request data. Dotted arrows are configuration and observability, which do
not sit on the request path.

The pipeline is strictly linear. Each stage has one responsibility and hands a typed object
to the next, so any stage can be tested in isolation.

---

## 2. Request Flow

```mermaid
sequenceDiagram
    participant HR as HR client
    participant API as FastAPI
    participant P as Parser
    participant F as Feature builder
    participant M as LambdaRank
    participant S as SHAP
    participant L as Logs / metrics

    HR->>API: POST /rank {job, [candidates]}
    API->>API: Validate with Pydantic
    API->>L: log request_start (request_id)

    loop for each candidate
        API->>P: parse(cv_text)
        P-->>API: ParsedProfile + warnings
        API->>F: build(profile, job)
        F-->>API: feature vector
    end

    API->>M: predict(feature matrix)
    M-->>API: raw relative scores
    API->>API: sort by score, assign ranks
    API->>S: shap_values(feature matrix)
    S-->>API: per-feature contributions
    API->>API: map contributions to reasons

    API->>L: log request_end (latency, count, model_version)
    API-->>HR: ranked candidates + explanations
```

Two details worth noting.

Ranks are assigned **after** sorting the whole set, not per candidate — ranking is inherently
a set operation, which is also why LambdaRank is the right objective.

SHAP runs on the full feature matrix in one call rather than per candidate. TreeExplainer is
vectorised, and a per-candidate loop would dominate the latency budget.

---

## 3. Training Pipeline

```mermaid
flowchart LR
    subgraph Gen["Data generation"]
        V["vocab.py<br/>certs, sites, shifts"]
        C["candidates.py<br/>5,000 candidates"]
        J["jobs.py<br/>200 postings"]
        LB["labels.py<br/>graded 0-3"]
        PR["protected.py<br/>SEPARATE STORE"]
    end

    subgraph Prep["Preparation"]
        PARSE2["Parse CV text"]
        FEAT2["Build pairwise features"]
        GRP["Group by job posting"]
        SPL["Group-level split"]
    end

    subgraph Train["Training"]
        BASE["baseline.py<br/>rule-based scorer"]
        LGB["train.py<br/>LightGBM lambdarank"]
        EV["evaluate.py<br/>NDCG / MAP / MRR"]
    end

    subgraph Audit["Audit and persist"]
        FAIR["fairness/audit.py"]
        SAVE["registry/artifacts.py<br/>models/v0.1.0/"]
    end

    V --> C --> LB
    V --> J --> LB
    C --> PARSE2 --> FEAT2
    J --> FEAT2
    LB --> GRP
    FEAT2 --> GRP --> SPL
    SPL --> BASE --> EV
    SPL --> LGB --> EV
    EV --> SAVE
    PR -.->|"evaluation only"| FAIR
    LGB --> FAIR --> SAVE
```

`protected.py` connects only to the fairness audit, with a dotted line, and never reaches
`FEAT2`. That absence is the whole point of the diagram.

The baseline and LambdaRank both feed the same evaluation step so that their scores are
computed on identical data with identical metrics.

---

## 4. Fairness Boundary

```mermaid
flowchart TB
    subgraph Allowed["Reaches the model"]
        A1["Years of experience"]
        A2["Certifications held"]
        A3["Shift availability"]
        A4["Prior role count"]
        A5["Site type experience"]
    end

    subgraph Blocked["Never reaches the model"]
        B1["Gender"]
        B2["Age / date of birth"]
        B3["Name"]
        B4["Nationality / ethnicity"]
        B5["Marital status"]
        B6["Photograph"]
        B7["Postcode"]
        B8["Graduation year"]
    end

    subgraph Watch["Allowed but monitored as proxies"]
        W1["Months since last role<br/>-> career breaks"]
        W2["Role count<br/>-> age"]
        W3["Shift availability<br/>-> caring responsibilities"]
    end

    FB["features/builder.py"]
    MODEL["LambdaRank model"]
    AUDIT["fairness/audit.py"]
    GATE["tests/test_leakage.py"]

    Allowed --> FB
    Watch --> FB
    FB --> MODEL
    Blocked -.->|"import barrier"| AUDIT
    Blocked -->|"any path here"| GATE
    GATE -->|"BUILD FAILS"| MODEL
    MODEL --> AUDIT
```

Three separate mechanisms appear here, and they are deliberately redundant.

The **import barrier** means protected attributes live in a module the feature package does
not import, so reaching them requires adding an import that does not exist.

The **leakage gate** is a test that fails the build if a blocked field appears in the feature
set anyway.

The **audit** measures outcomes by group, catching indirect discrimination through proxies
that neither of the first two mechanisms can see.

Prevention alone is insufficient because proxies exist. Measurement alone is insufficient
because it only detects harm after it has been learned.

---

## 5. Module Dependencies

```mermaid
flowchart BT
    core["core<br/>config, logging, metrics"]
    schemas["schemas<br/>Pydantic models"]
    data["data<br/>generator"]
    parsing["parsing"]
    features["features"]
    ranking["ranking"]
    explain["explain"]
    fairness["fairness"]
    registry["registry"]
    api["api"]

    schemas --> core
    data --> schemas
    parsing --> schemas
    features --> schemas
    features --> parsing
    ranking --> features
    explain --> ranking
    fairness --> ranking
    registry --> ranking
    api --> registry
    api --> explain
    api --> parsing
    api --> core
```

Arrows point from dependent to dependency. The graph is acyclic, and `core` and `schemas` sit
at the bottom with no dependencies of their own.

`features` does not depend on `data`. This matters: the feature builder must work identically
on generated training data and on real CV text arriving through the API, so it cannot know
anything about how training data was produced.

---

## 6. Deployment

```mermaid
flowchart TB
    subgraph Dev["Development"]
        LOCAL["conda env guardmatch<br/>Python 3.12"]
    end

    subgraph CI["GitHub Actions"]
        LINT["ruff"]
        TYPE["mypy"]
        TEST["pytest<br/>incl. fairness + leakage gates"]
        BUILD["docker build"]
    end

    subgraph Runtime["Container"]
        subgraph IMG["Image"]
            APP["FastAPI + uvicorn<br/>non-root user"]
            ART["models/v0.1.0/<br/>baked in"]
            SPACY["en_core_web_sm"]
        end
        HC["Health checks<br/>/health, /ready"]
    end

    LOCAL -->|"git push"| LINT --> TYPE --> TEST --> BUILD
    BUILD --> IMG
    HC -.->|"gates traffic"| APP
```

Model artifacts are baked into the image rather than mounted, so a running container fully
describes the model it is serving. Rolling out a new model means deploying a new image, which
keeps the deployment history and the model history in step.

The readiness probe fails until the model has loaded and its checksums have verified, so an
instance whose artifacts are broken never receives traffic.
