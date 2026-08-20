# GuardMatch AI — Architecture

**Companion to:** [design-doc.md](design-doc.md)
**Date:** 2026-08-15

This document holds the structural view of the system: how components fit together, how a
request flows, how the model is trained, and where the boundaries that protect fairness are
drawn.

Module and test paths in the diagrams below are written in shorthand and are relative to
`backend/` — `features/builder.py` means `backend/src/guardmatch/features/builder.py`. Paths
shown inside the container are the container's own, not the repository's.

---

## 1. System Overview

```mermaid
flowchart TB
    subgraph Browser["Browser"]
        UI["Rank workspace<br/>posting, applications,<br/>ranked list + explanations"]
    end

    subgraph Web["Next.js server"]
        PROXY["Route handler /api/*<br/>endpoint allowlist<br/>status and body forwarded unchanged"]
    end

    subgraph API["FastAPI service"]
        MW["Middleware<br/>request_id, timing, logging"]
        RT["Scoring routes<br/>/rank /score /parse"]
        INTK["Intake routes<br/>/extract /sample-candidates<br/>no model dependency"]
        TRAN["Transparency routes<br/>/fairness /feature-importance /model-info"]
        OPS["Operational routes<br/>/health /ready /metrics"]
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

    UI -->|"POST /api/rank, /api/extract<br/>GET /api/sample-candidates, /api/ready<br/>same origin"| PROXY
    PROXY -->|"server-side"| MW
    MW --> RT
    MW --> INTK
    MW --> TRAN
    MW --> OPS
    RT --> PARSE --> FEAT --> RANK --> EXPL
    EXPL -->|"ranked list + reasons"| RT
    RT -->|"JSON response"| PROXY
    PROXY -->|"status and body unchanged"| UI

    REG -.->|"loaded once at startup"| RANK
    REG -.->|"feature contract check"| FEAT
    REG -.->|"audit and metadata, read not computed"| TRAN

    MW -.-> LOG
    RT -.-> MET
    PARSE -.-> MET
    RANK -.-> MET
```

Solid arrows carry request data. Dotted arrows are configuration and observability, which do
not sit on the request path.

The pipeline is strictly linear. Each stage has one responsibility and hands a typed object
to the next, so any stage can be tested in isolation.

**The routes are grouped by what they depend on, not by what they are about.** Scoring routes
need a verified model and return `503` without one. Intake routes — `/extract` and
`/sample-candidates` — read a file or generate text, so they answer while the model is still
verifying; a caller can prepare a batch before the service is able to score it. Transparency
routes report what the loaded artifact already carries and compute no new claim about it, which is
why the registry has a dotted arrow to them rather than a solid one.

**Transparency routes have no arrow from the browser.** `/fairness` and `/feature-importance`
answer for server-side callers and for anyone inspecting the service directly; no page renders
them, so they are not in the proxy's allowlist. A dashboard over them was built and removed —
see [the frontend notes](frontend.md) — and the routes outliving the page is the point: the
fairness position is a property of the service, not of a screen.

**The browser has no arrow to the FastAPI service.** Every call it makes goes to the Next.js
route handler on its own origin, which makes the onward call server-side. That is the whole
reason no CORS configuration exists anywhere in the backend: there is no cross-origin request
to permit. The alternative — naming every origin allowed to reach a hiring model — fails
silently when the list is later wrong, because nothing appears broken while access widens.

The handler carries an endpoint allowlist rather than forwarding whatever it is handed.
Without one it is an open relay to everything the service exposes, `/metrics` included, from
any page able to reach this one.

An HR system integrating directly against the API is still a supported caller. It simply does
not appear here, because it does not go through the browser.

---

## 2. Request Flow

```mermaid
sequenceDiagram
    participant B as Browser
    participant W as Next.js handler
    participant API as FastAPI
    participant P as Parser
    participant F as Feature builder
    participant M as LambdaRank
    participant S as SHAP
    participant L as Logs / metrics

    B->>B: Validate locally: enums, 20k chars, unique ids, 500 batch
    B->>W: POST /api/rank + X-Request-ID
    W->>W: Check the endpoint allowlist
    W->>API: POST /rank {job, [candidates]}
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
    API-->>W: ranked candidates + explanations + disclaimer
    W-->>B: status and body unchanged
    B->>B: Re-check base_value + contributions = score
    B->>B: Render reasons, 12 bars, warnings, disclaimer
```

The browser validates first, against the same limits the service enforces, so a reviewer meets
a ceiling while typing rather than through a `422`. It is not a substitute for the boundary
check: the service still rejects anything that reaches it malformed, and the client cannot be
trusted to have run.

The last two steps are the point of the whole system. SHAP here is additive — base value plus
every contribution reconstructs the score — so the browser recomputes the sum and displays
whether it holds. Measured deltas run from 0.0e+00 to 1.8e-15, which is JSON rounding rather
than disagreement. An explanation that does not add up to the score it explains is a story
printed beside a number, and the interface can say which one it is holding.

`X-Request-ID` is generated by the browser, preserved by the handler, and echoed by the service
into both the response body and every log line for that request. One identifier therefore spans
all three, which is what turns "the ranking looked wrong" into a report someone can trace.

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
    UI["Rank workspace<br/>labels proxy rows in the explanation"]

    Allowed --> FB
    Watch --> FB
    FB --> MODEL
    Blocked -.->|"import barrier"| AUDIT
    Blocked -->|"any path here"| GATE
    GATE -->|"BUILD FAILS"| MODEL
    MODEL --> AUDIT
    Watch -.->|"named at the point of use"| UI
    MODEL --> UI
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

A fourth, weaker mechanism sits in the interface. Each monitored proxy row in the contribution
table is labelled `(proxy)` with its specific exposure, so a reviewer sees that
`shift_match` — the model's single largest input — carries a correlation with caring
responsibilities at the moment it is acting on a candidate, rather than only in the fairness
report. This prevents nothing on its own; it moves a fact from a document nobody has open into
the screen where the decision is being made.

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

Arrows point from a module to what it depends on. The graph is acyclic by construction and the
`fairness` package is deliberately a leaf that nothing on the scoring path imports — a static test
fails the build if any module reachable from `api` ever imports where the demographics live.

**The frontend is a second graph, and the two meet at exactly one place.**

```mermaid
flowchart BT
    types["types.ts<br/>the API contract, mirrored by hand"]
    errors["errors.ts<br/>both 422 shapes, 503"]
    api2["api.ts<br/>typed client"]
    proxy["proxy.ts<br/>endpoint allowlist"]
    files["files.ts<br/>intake, two size bounds"]
    reqs["requirements.ts<br/>asked vs shown"]
    shortlist["shortlist.ts<br/>filter, sort, CSV"]
    feats["features.ts<br/>feature metadata, additivity"]
    route["app/api/[...path]<br/>route handler"]
    page["app/page.tsx<br/>the workspace"]
    comps["components/*"]

    errors --> types
    api2 --> types
    api2 --> errors
    files --> types
    files --> api2
    reqs --> types
    shortlist --> types
    feats --> types
    route --> proxy
    comps --> types
    comps --> feats
    comps --> reqs
    comps --> shortlist
    page --> api2
    page --> files
    page --> comps
```

`types.ts` is the root of the frontend graph and is **hand-written rather than generated** from the
OpenAPI schema. That is a deliberate cost: a generated client would track the contract
automatically and would also import whatever the schema happened to say, including fields the
interface must never send. Writing it by hand makes `Candidate` a type that *cannot* carry a
display name, which is what turns the leakage rule into something the compiler enforces.

The only edge between the two graphs is the route handler reaching the service over HTTP. No
frontend module imports anything Python, and no backend module knows the frontend exists — which
is what makes the trust boundary in section 1 a boundary rather than a convention.

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

    subgraph CI["GitHub Actions — 5 jobs"]
        LINT["ruff + mypy"]
        TEST["pytest<br/>399 tests"]
        GATES["gates as their own job<br/>80 tests"]
        WEB["frontend<br/>lint, types, tests, build"]
        BUILD["docker build<br/>both images, both started"]
    end

    subgraph Runtime["Compose stack"]
        subgraph IMGA["guardmatch-ai  1.37 GB"]
            APP["FastAPI + uvicorn"]
            ART["models/v0.1.0/<br/>baked in"]
            SPACY["en_core_web_sm"]
        end
        subgraph IMGW["guardmatch-web  325 MB"]
            NEXT["Next.js standalone"]
        end
        HC["/ready<br/>model loaded and verified"]
    end

    LOCAL -->|"git push"| LINT
    LOCAL --> TEST
    LOCAL --> GATES
    LOCAL --> WEB
    LINT --> BUILD
    TEST --> BUILD
    WEB --> BUILD
    BUILD --> IMGA
    BUILD --> IMGW
    HC -.->|"gates traffic"| APP
    NEXT -->|"BACKEND_URL=http://api:8000"| APP
```

Model artifacts are baked into the image rather than mounted, so a running container fully
describes the model it is serving. Rolling out a new model means deploying a new image, which
keeps the deployment history and the model history in step.

The readiness probe fails until the model has loaded and its checksums have verified, so an
instance whose artifacts are broken never receives traffic. `web` waits on that probe rather
than on the API process starting, so a reviewer never arrives at a workspace whose backend
cannot answer.

Two build contexts rather than one. `guardmatch-ai` is built from `backend/` and
`guardmatch-web` from `frontend/`, so neither image can grow by picking up the other half of
the repository. Both run as uid 1001 on a read-only root filesystem with `no-new-privileges` —
the same posture on both sides, because a stack is only as constrained as its least
constrained container.

**The verification that matters here failed silently for eleven days.** `models/v0.1.0` was
written on Windows, so its recorded checksums described bytes containing CRLF; git normalised
them to LF, and the artifact then failed verification on every Linux checkout — CI, this
container, and any contributor not on Windows. Startup re-raises by design, so the service
refused to serve. It passed only on the machine that produced the bytes. Artifacts are now
written with LF on every platform and `.gitattributes` marks them `-text`; two tests assert
that no artifact file contains CRLF, one of them checking the artifact **as committed** rather
than one a fixture regenerated. See the model card, section 9.
