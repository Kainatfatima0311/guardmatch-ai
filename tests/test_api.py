"""API contract tests.

The tests here fall into three groups.

**Contract shape.** Every scoring response must carry the model version, the
score type, and an explanation. These are what let a caller interpret and trace a
result without consulting anything else, and they are easy to drop by accident
during a refactor.

**Readiness semantics.** ``/health`` must answer without touching the model and
``/ready`` must return 503 until the model is verified. Getting these the wrong
way round turns a model problem into a container restart loop.

**Rejection at the boundary.** Malformed input, oversized batches and duplicate
ids must be refused before any work begins. A validation gap here is not a
cosmetic problem: an unbounded batch is an availability risk on a public
endpoint.

The service state is constructed directly rather than through the lifespan, so
these tests need no artifact on disk and train a small model in seconds.
"""

from __future__ import annotations

from typing import Any

import lightgbm as lgb
import numpy as np
import pytest
from fastapi.testclient import TestClient

from guardmatch.api.app import create_app
from guardmatch.api.dependencies import ServiceState
from guardmatch.explain.shap_explainer import Explainer
from guardmatch.features.registry import FEATURE_NAMES
from guardmatch.ranking.predict import Ranker
from guardmatch.schemas.scoring import SCORE_TYPE

CV_TEXT = """PROFILE
Reliable security officer with 6 years of experience.

CERTIFICATIONS
- SIA licence
- fire marshal
- IOSH Working Safely

AVAILABILITY
Available for night shifts and rotating shifts.

EMPLOYMENT
Site Security Officer, Acme Ltd (2024 - present) - construction site

ADDITIONAL
Full clean driving licence"""

SPARSE_CV = "PROFILE\nSeeking a security position."

JOB: dict[str, Any] = {
    "job_id": "j_test",
    "required_certifications": ["security_licence", "fire_safety", "health_and_safety"],
    "min_years_experience": 4.0,
    "shift_pattern": "night",
    "site_type": "construction",
    "driving_required": True,
}


@pytest.fixture(scope="module")
def booster() -> lgb.Booster:
    """A small ranker, so the API tests do not depend on a released artifact."""
    rng = np.random.default_rng(7)
    rows = 120
    features = rng.random((rows, len(FEATURE_NAMES)))
    labels = np.clip(
        (features[:, 2] * 2 + features[:, 6] * 1.5 + rng.random(rows) * 0.4).round(), 0, 3
    ).astype(int)

    dataset = lgb.Dataset(features, label=labels, group=[20] * 6, free_raw_data=False)
    return lgb.train(
        {
            "objective": "lambdarank",
            "metric": "ndcg",
            "num_leaves": 7,
            "verbosity": -1,
            "seed": 7,
        },
        dataset,
        num_boost_round=20,
    )


@pytest.fixture
def ready_client(booster: lgb.Booster) -> TestClient:
    """A client whose service is loaded and ready."""
    app = create_app()
    app.state.service = ServiceState(
        model_version="v-test",
        loaded=None,
        ranker=Ranker(booster),
        explainer=Explainer(booster),
        ready=True,
        detail=None,
    )
    return TestClient(app)


@pytest.fixture
def unready_client() -> TestClient:
    """A client whose model has not loaded — the state before startup completes."""
    app = create_app()
    app.state.service = ServiceState(
        model_version="v-test", ready=False, detail="checksum verification failed"
    )
    return TestClient(app)


def candidate(candidate_id: str = "c_1", text: str = CV_TEXT) -> dict[str, str]:
    return {"candidate_id": candidate_id, "cv_text": text}


# ---------------------------------------------------------------------------
# Liveness and readiness
# ---------------------------------------------------------------------------


def test_health_answers_without_the_model(unready_client: TestClient) -> None:
    """Liveness must not depend on the model.

    If it did, a model problem would restart the container in a loop instead of
    removing the instance from the pool.
    """
    response = unready_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_reports_503_until_the_model_is_verified(unready_client: TestClient) -> None:
    response = unready_client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["ready"] is False
    assert "checksum" in body["detail"]


def test_ready_reports_200_when_loaded(ready_client: TestClient) -> None:
    response = ready_client.get("/ready")
    assert response.status_code == 200
    assert response.json()["ready"] is True


def test_scoring_is_refused_while_unready(unready_client: TestClient) -> None:
    """503 rather than 500 — the caller did nothing wrong and may retry."""
    response = unready_client.post("/rank", json={"job": JOB, "candidates": [candidate()]})
    assert response.status_code == 503


def test_model_info_reports_the_version(ready_client: TestClient) -> None:
    response = ready_client.get("/model-info")
    assert response.json()["model_version"] == "v-test"


def test_metrics_endpoint_serves_prometheus(ready_client: TestClient) -> None:
    response = ready_client.get("/metrics")
    assert response.status_code == 200
    assert "guardmatch_requests_total" in response.text


# ---------------------------------------------------------------------------
# Parse
# ---------------------------------------------------------------------------


def test_parse_returns_structured_facts(ready_client: TestClient) -> None:
    response = ready_client.post("/parse", json={"candidate": candidate()})
    assert response.status_code == 200

    profile = response.json()["profile"]
    assert profile["years_experience"] == 6.0
    assert "security_licence" in profile["certifications"]
    assert profile["driving_licence"] is True


def test_parse_reports_unknowns_as_null_with_warnings(ready_client: TestClient) -> None:
    """Unknown must not arrive at the caller as a zero or a false."""
    response = ready_client.post("/parse", json={"candidate": candidate(text=SPARSE_CV)})
    profile = response.json()["profile"]

    assert profile["years_experience"] is None
    assert profile["driving_licence"] is None
    assert profile["previous_role_count"] is None
    assert profile["parse_warnings"]


# ---------------------------------------------------------------------------
# Score
# ---------------------------------------------------------------------------


def test_score_returns_no_rank(ready_client: TestClient) -> None:
    """A rank of 1 out of 1 would imply a comparison that never happened."""
    response = ready_client.post("/score", json={"job": JOB, "candidate": candidate()})
    assert response.status_code == 200

    body = response.json()
    assert "rank" not in body
    assert body["score_type"] == SCORE_TYPE
    assert body["explanation"]["contributions"]
    assert body["explanation"]["reasons"]


def test_score_carries_the_request_id(ready_client: TestClient) -> None:
    """The id is what makes a decision reconstructable from logs later."""
    response = ready_client.post("/score", json={"job": JOB, "candidate": candidate()})
    assert response.headers["X-Request-ID"]
    assert response.json()["request_id"] == response.headers["X-Request-ID"]


def test_inbound_request_id_is_preserved(ready_client: TestClient) -> None:
    """A caller-supplied id must survive, so a trace can span services."""
    response = ready_client.post(
        "/score",
        json={"job": JOB, "candidate": candidate()},
        headers={"X-Request-ID": "trace-abc-123"},
    )
    assert response.headers["X-Request-ID"] == "trace-abc-123"


# ---------------------------------------------------------------------------
# Rank
# ---------------------------------------------------------------------------


def test_rank_orders_best_first(ready_client: TestClient) -> None:
    candidates = [
        candidate("c_strong", CV_TEXT),
        candidate("c_weak", SPARSE_CV),
        candidate("c_mid", "PROFILE\n5 years of experience.\n\nCERTIFICATIONS\n- SIA licence"),
    ]
    response = ready_client.post("/rank", json={"job": JOB, "candidates": candidates})
    assert response.status_code == 200

    ranked = response.json()["candidates"]
    assert [entry["rank"] for entry in ranked] == [1, 2, 3]

    scores = [entry["relative_ranking_score"] for entry in ranked]
    assert scores == sorted(scores, reverse=True)


def test_every_ranked_candidate_carries_an_explanation(ready_client: TestClient) -> None:
    """Explainability is not optional — there is no flag to turn it off."""
    candidates = [candidate(f"c_{index}") for index in range(5)]
    response = ready_client.post("/rank", json={"job": JOB, "candidates": candidates})

    for entry in response.json()["candidates"]:
        assert entry["explanation"]["contributions"]
        assert entry["explanation"]["reasons"]
        assert entry["score_type"] == SCORE_TYPE


def test_rank_response_carries_the_disclaimer(ready_client: TestClient) -> None:
    """The constraint travels with the data rather than living only in docs."""
    response = ready_client.post("/rank", json={"job": JOB, "candidates": [candidate()]})
    disclaimer = response.json()["disclaimer"]

    assert "not probabilities" in disclaimer
    assert "not a hiring decision" in disclaimer


def test_parse_warnings_reach_the_ranked_candidate(ready_client: TestClient) -> None:
    """A reviewer must be able to see where the system was unsure."""
    response = ready_client.post(
        "/rank", json={"job": JOB, "candidates": [candidate("c_sparse", SPARSE_CV)]}
    )
    assert response.json()["candidates"][0]["parse_warnings"]


# ---------------------------------------------------------------------------
# Rejection at the boundary
# ---------------------------------------------------------------------------


def test_empty_cv_is_rejected(ready_client: TestClient) -> None:
    response = ready_client.post(
        "/rank", json={"job": JOB, "candidates": [candidate("c_x", "   ")]}
    )
    assert response.status_code == 422


def test_empty_candidate_list_is_rejected(ready_client: TestClient) -> None:
    response = ready_client.post("/rank", json={"job": JOB, "candidates": []})
    assert response.status_code == 422


def test_duplicate_candidate_ids_are_rejected(ready_client: TestClient) -> None:
    """Duplicates would produce two rows for one person and distort the ranking."""
    response = ready_client.post(
        "/rank", json={"job": JOB, "candidates": [candidate("dup"), candidate("dup")]}
    )
    assert response.status_code == 422


def test_oversized_batch_is_rejected(ready_client: TestClient) -> None:
    """An unbounded batch is an availability risk on a public endpoint."""
    candidates = [candidate(f"c_{index}", SPARSE_CV) for index in range(600)]
    response = ready_client.post("/rank", json={"job": JOB, "candidates": candidates})
    assert response.status_code == 422
    assert "MAX_RANK_BATCH" in response.text


def test_unknown_field_is_rejected(ready_client: TestClient) -> None:
    """`extra="forbid"` means a stray field cannot slip through unnoticed.

    Notably, this is what stops a caller from attaching a demographic field to a
    candidate payload and having it silently ignored — it is refused instead.
    """
    response = ready_client.post(
        "/score",
        json={"job": JOB, "candidate": {**candidate(), "gender": "female"}},
    )
    assert response.status_code == 422


def test_invalid_enum_value_is_rejected(ready_client: TestClient) -> None:
    response = ready_client.post(
        "/rank",
        json={"job": {**JOB, "shift_pattern": "whenever"}, "candidates": [candidate()]},
    )
    assert response.status_code == 422


def test_openapi_schema_is_served(ready_client: TestClient) -> None:
    """The Swagger UI is the project's interface in place of a frontend."""
    schema = ready_client.get("/openapi.json").json()
    assert "/rank" in schema["paths"]
    assert "/score" in schema["paths"]
    assert "/parse" in schema["paths"]
