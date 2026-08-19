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

import io
from typing import Any

import lightgbm as lgb
import numpy as np
import pypdf
import pytest
from fastapi.testclient import TestClient

from guardmatch.api.app import create_app
from guardmatch.api.dependencies import ServiceState
from guardmatch.explain.shap_explainer import Explainer
from guardmatch.features.registry import FEATURE_NAMES
from guardmatch.ranking.predict import Ranker
from guardmatch.registry.artifacts import LoadedModel
from guardmatch.registry.metadata import ModelMetadata
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


def _group(name: str, appearances: int, in_top_k: int) -> dict[str, Any]:
    return {
        "group": name,
        "n_appearances": appearances,
        "n_in_top_k": in_top_k,
        "n_qualified": appearances // 3,
        "n_qualified_in_top_k": in_top_k // 2,
        "selection_rate": in_top_k / appearances,
        "qualified_selection_rate": (in_top_k // 2) / max(appearances // 3, 1),
        "mean_exposure": 0.24,
    }


# A two-attribute audit shaped like the released one, and deliberately carrying
# **both** outcomes the endpoint has to keep distinct: `gender` passes cleanly,
# while `age_band` sits below the four-fifths line yet is reported inconclusive
# rather than failed, because the gap is not distinguishable from noise once
# corrected for the number of possible group comparisons. A fixture where
# everything simply passes could not catch a consumer that collapses the two.
AUDIT: dict[str, Any] = {
    "model_version": "v-test",
    "top_k": 10,
    "adverse_impact_threshold": 0.8,
    "max_gap": 0.1,
    "min_group_size": 30,
    "n_postings": 50,
    "n_rows": 3041,
    "passes": True,
    "failures": [],
    "inconclusive": [
        "age_band: adverse impact ratio 0.627 is below the four-fifths threshold "
        "of 0.80 but not distinguishable from noise once corrected for 10 possible "
        "group comparisons (p=0.0069, threshold 0.0050); smallest group n=319"
    ],
    "attributes": [
        {
            "attribute": "gender",
            "top_k": 10,
            "groups": [_group("female", 1275, 214), _group("male", 1766, 306)],
            "suppressed_groups": [],
            "adverse_impact_ratio": 0.9649,
            "demographic_parity_gap": 0.0059,
            "equal_opportunity_gap": 0.0389,
            "exposure_ratio": 0.9825,
            "selection_p_value": 0.6652,
            "qualified_p_value": 0.2067,
            "significance_threshold": 0.05,
            "n_comparisons": 1,
            "passes": True,
            "failures": [],
            "inconclusive": [],
        },
        {
            "attribute": "age_band",
            "top_k": 10,
            "groups": [
                _group("under_25", 319, 33),
                _group("25_34", 902, 148),
                _group("55_plus", 421, 44),
            ],
            "suppressed_groups": ["unknown"],
            "adverse_impact_ratio": 0.6275,
            "demographic_parity_gap": 0.0612,
            "equal_opportunity_gap": 0.0904,
            "exposure_ratio": 0.9077,
            "selection_p_value": 0.0069,
            "qualified_p_value": 0.0411,
            "significance_threshold": 0.005,
            "n_comparisons": 10,
            "passes": True,
            "failures": [],
            "inconclusive": [
                "adverse impact ratio 0.627 is below 0.80 but not distinguishable "
                "from noise after correcting for 10 comparisons"
            ],
        },
    ],
}


@pytest.fixture
def audited_client(booster: lgb.Booster) -> TestClient:
    """A client whose artifact carries a fairness audit.

    `ready_client` is ready but holds no `LoadedModel`, which is enough for the
    scoring routes and not for anything reading the artifact bundle. The audit
    lives in that bundle, so it needs a loaded artifact rather than a relaxed
    endpoint.
    """
    app = create_app()
    metadata = ModelMetadata(
        model_version="v-test",
        trained_at="2026-08-20T00:00:00+00:00",
        generator_version="1.0.0",
        data_seed=42,
        n_candidates=100,
        n_jobs=10,
        n_pairs=400,
        n_train_groups=8,
        n_valid_groups=2,
        feature_names=list(FEATURE_NAMES),
        hyperparameters={"num_leaves": 7},
        best_iteration=20,
        git_sha="abc123",
        git_dirty=False,
    )
    app.state.service = ServiceState(
        model_version="v-test",
        loaded=LoadedModel(
            booster=booster,
            metadata=metadata,
            metrics={"model_ndcg_at_10": 0.9},
            fairness=AUDIT,
            feature_names=FEATURE_NAMES,
            version="v-test",
        ),
        ranker=Ranker(booster),
        explainer=Explainer(booster),
        ready=True,
        detail=None,
    )
    return TestClient(app)


@pytest.fixture
def unaudited_client(booster: lgb.Booster) -> TestClient:
    """An artifact with no audit — `train` writes the model, `audit` fills this in."""
    app = create_app()
    metadata = ModelMetadata(
        model_version="v-test",
        trained_at="2026-08-20T00:00:00+00:00",
        generator_version="1.0.0",
        data_seed=42,
        n_candidates=100,
        n_jobs=10,
        n_pairs=400,
        n_train_groups=8,
        n_valid_groups=2,
        feature_names=list(FEATURE_NAMES),
        hyperparameters={},
        best_iteration=20,
        git_sha="abc123",
        git_dirty=False,
    )
    app.state.service = ServiceState(
        model_version="v-test",
        loaded=LoadedModel(
            booster=booster,
            metadata=metadata,
            metrics={},
            fairness={},
            feature_names=FEATURE_NAMES,
            version="v-test",
        ),
        ranker=Ranker(booster),
        explainer=Explainer(booster),
        ready=True,
        detail=None,
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


# ---------------------------------------------------------------------------
# document upload
# ---------------------------------------------------------------------------


def test_extract_reads_a_text_file(unready_client: TestClient) -> None:
    """Deliberately on the unready client.

    Extraction reads a file and touches nothing the model owns, so it must stay
    available while the model is still verifying — a reviewer can prepare a batch
    before the service can score it. If this ever returns 503, a dependency was
    added that does not belong.
    """
    response = unready_client.post(
        "/extract",
        files={"file": ("cv.txt", b"PROFILE\nGuard with 6 years.", "text/plain")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["filename"] == "cv.txt"
    assert "PROFILE" in body["cv_text"]
    assert body["source"] == "text"
    assert body["characters"] == len(body["cv_text"])


def test_extract_refuses_a_scanned_pdf_with_a_string_detail(ready_client: TestClient) -> None:
    """The failure the whole feature is shaped around, at the API boundary.

    `ParsingError` maps to a 422 whose `detail` is a **string**, unlike a
    validation 422 whose detail is an array. The client handles both; this pins
    that an unreadable file arrives as the string kind, since that is the one
    carrying a message meant for a person.
    """
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=595, height=842)
    buffer = io.BytesIO()
    writer.write(buffer)

    response = ready_client.post(
        "/extract",
        files={"file": ("scan.pdf", buffer.getvalue(), "application/pdf")},
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert isinstance(detail, str)
    assert "no text layer" in detail


def test_extract_never_returns_empty_text(ready_client: TestClient) -> None:
    """The invariant everything downstream relies on.

    Either text comes back and can be ranked, or an error comes back and the
    caller knows not to rank. There is no third state where something empty flows
    on looking like a CV.
    """
    response = ready_client.post(
        "/extract", files={"file": ("blank.txt", b"   \n  ", "text/plain")}
    )

    assert response.status_code == 422
    assert "empty" in response.json()["detail"]


def test_extract_output_is_rankable(ready_client: TestClient) -> None:
    """What comes out of /extract goes straight into /rank, unchanged."""
    extracted = ready_client.post(
        "/extract",
        files={
            "file": (
                "aisha.txt",
                b"PROFILE\nGuard with 6 years.\n\nCERTIFICATIONS\n- SIA licence",
                "text/plain",
            )
        },
    ).json()

    response = ready_client.post(
        "/rank",
        json={
            "job": JOB,
            "candidates": [{"candidate_id": "c_1", "cv_text": extracted["cv_text"]}],
        },
    )

    assert response.status_code == 200
    assert response.json()["candidates"][0]["rank"] == 1


def test_extract_does_not_echo_the_filename_into_the_ranking_path(
    ready_client: TestClient,
) -> None:
    """`/extract` returns the filename; `/rank` must never receive it.

    The filename is the display label, and `name` is a blocked attribute in this
    system. Attaching it to a candidate is refused by `extra="forbid"` — asserted
    here so the two endpoints cannot be wired together carelessly.
    """
    extracted = ready_client.post(
        "/extract", files={"file": ("aisha_okafor.txt", b"PROFILE\nGuard.", "text/plain")}
    ).json()

    response = ready_client.post(
        "/rank",
        json={
            "job": JOB,
            "candidates": [
                {
                    "candidate_id": "c_1",
                    "cv_text": extracted["cv_text"],
                    "filename": extracted["filename"],
                }
            ],
        },
    )

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# global feature importance
# ---------------------------------------------------------------------------


def test_feature_importance_covers_every_feature(ready_client: TestClient) -> None:
    response = ready_client.get("/feature-importance")

    assert response.status_code == 200
    body = response.json()
    assert len(body["features"]) == len(FEATURE_NAMES)
    assert {f["feature"] for f in body["features"]} == set(FEATURE_NAMES)


def test_feature_importance_shares_sum_to_one(ready_client: TestClient) -> None:
    """Shares, not raw magnitudes.

    The model card quotes these as percentages, so the response has to carry
    something that can be read as one. A raw mean absolute contribution cannot:
    nobody can scale it without the total.
    """
    body = ready_client.get("/feature-importance").json()

    assert sum(f["share"] for f in body["features"]) == pytest.approx(1.0)


def test_feature_importance_is_ordered_by_effect(ready_client: TestClient) -> None:
    """Largest first, because the question is which feature dominates."""
    shares = [f["share"] for f in ready_client.get("/feature-importance").json()["features"]]

    assert shares == sorted(shares, reverse=True)


def test_feature_importance_is_refused_while_unready(unready_client: TestClient) -> None:
    """It needs the explainer, so it is a scoring-path route and answers like one."""
    assert unready_client.get("/feature-importance").status_code == 503


def test_feature_importance_is_cached(ready_client: TestClient) -> None:
    """The same answer twice, from the cache rather than recomputed.

    Building the sample means parsing 200 CVs — around a second. Acceptable once
    for a page a reviewer opens; not acceptable on every refresh.
    """
    first = ready_client.get("/feature-importance").json()
    again = ready_client.get("/feature-importance").json()

    assert first == again


# ---------------------------------------------------------------------------
# fairness audit
# ---------------------------------------------------------------------------


def test_fairness_reports_a_missing_audit_plainly(unaudited_client: TestClient) -> None:
    """404 with instructions, not an empty shape.

    An artifact can legitimately exist without an audit — `train` writes the model
    and `audit` fills this in afterwards. Returning an empty audit would read like
    a clean bill of health for a model nobody has measured.
    """
    response = unaudited_client.get("/fairness")

    assert response.status_code == 404
    assert "guardmatch audit" in response.json()["detail"]


def test_fairness_is_refused_while_unready(unready_client: TestClient) -> None:
    """503 rather than 404.

    The audit is part of the artifact bundle, so its absence before load means the
    service is not ready — not that fairness data does not exist. A 404 would send
    a caller looking for a missing file.
    """
    response = unready_client.get("/fairness")

    assert response.status_code == 503


def test_fairness_returns_the_audit(audited_client: TestClient) -> None:
    response = audited_client.get("/fairness")

    assert response.status_code == 200
    body = response.json()
    assert body["model_version"] == "v-test"
    assert body["top_k"] == 10
    assert body["adverse_impact_threshold"] == 0.8


def test_fairness_reports_every_audited_attribute(audited_client: TestClient) -> None:
    body = audited_client.get("/fairness").json()

    assert [a["attribute"] for a in body["attributes"]] == ["gender", "age_band"]


def test_fairness_carries_group_level_aggregates(audited_client: TestClient) -> None:
    """Aggregates, and only aggregates.

    This endpoint is publishable precisely because nothing in it describes an
    individual. If a candidate id or CV text ever appeared here it would be a
    disclosure, not a metric — asserted on the whole serialised body rather than
    field by field.
    """
    response = audited_client.get("/fairness")

    assert "candidate_id" not in response.text
    assert "cv_text" not in response.text

    group = response.json()["attributes"][0]["groups"][0]
    assert set(group) == {
        "group",
        "n_appearances",
        "n_in_top_k",
        "n_qualified",
        "n_qualified_in_top_k",
        "selection_rate",
        "qualified_selection_rate",
        "mean_exposure",
    }


def test_fairness_distinguishes_inconclusive_from_passing(audited_client: TestClient) -> None:
    """The distinction the whole endpoint exists to preserve.

    `passes` is not `adverse_impact_ratio >= threshold`. A ratio below the
    four-fifths line that is not distinguishable from noise after Bonferroni
    correction is reported as **inconclusive**, and the released `age_band` audit
    is exactly that case at 0.627. A consumer rendering `passes` as a green tick
    while ignoring `inconclusive` would state something this audit does not, so
    both fields have to survive the boundary.
    """
    body = audited_client.get("/fairness").json()
    by_name = {a["attribute"]: a for a in body["attributes"]}

    clean = by_name["gender"]
    assert clean["passes"] is True
    assert clean["inconclusive"] == []

    unclear = by_name["age_band"]
    assert unclear["adverse_impact_ratio"] < body["adverse_impact_threshold"]
    # Below the line and still `passes`, because it is inconclusive rather than a
    # breach. Anything rendering only `passes` would call this clean.
    assert unclear["passes"] is True
    assert len(unclear["inconclusive"]) == 1
    assert unclear["failures"] == []

    # The run reports no failures while still carrying an inconclusive result, so
    # a summary built from `failures` alone would lose it.
    assert body["failures"] == []
    assert len(body["inconclusive"]) == 1


def test_fairness_includes_the_exposure_metric(audited_client: TestClient) -> None:
    """Exposure is the metric that earns its place.

    Two groups shortlisted at exactly equal rates but placed 1-5 against 6-10 read
    as perfectly fair on every selection-rate measure. Only exposure catches it, so
    it must not be dropped from the response for being the unfamiliar one.
    """
    attribute = audited_client.get("/fairness").json()["attributes"][0]

    assert "exposure_ratio" in attribute
    assert 0.0 <= attribute["exposure_ratio"] <= 2.0


# ---------------------------------------------------------------------------
# sample candidates
# ---------------------------------------------------------------------------


def test_sample_candidates_returns_the_requested_count(ready_client: TestClient) -> None:
    response = ready_client.get("/sample-candidates?count=7")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 7
    assert len(body["candidates"]) == 7


def test_sample_candidates_never_returns_ground_truth(ready_client: TestClient) -> None:
    """The generator knows the answers. A caller must not.

    `generate_candidates` returns `GeneratedCandidate`, which carries the `true_*`
    values the CV text was written from — years, certifications, availability.
    Returning those would hand a caller exactly what the model is supposed to infer
    from the text, and any demo built on it would be measuring nothing.

    Asserted on the raw response body as well as the parsed fields, because the
    leak would happen in serialisation and a field-by-field check on a parsed
    object can miss a nested one.
    """
    response = ready_client.get("/sample-candidates?count=3")

    for candidate in response.json()["candidates"]:
        assert set(candidate) == {"candidate_id", "cv_text"}, (
            f"unexpected fields crossed the boundary: {sorted(candidate)}"
        )

    assert "true_" not in response.text


def test_sample_candidates_marks_itself_synthetic(ready_client: TestClient) -> None:
    """Stated in the payload, not only in the documentation.

    Same argument as the disclaimer on `RankResponse`: a constraint that travels
    with the data cannot be left behind by a caller who never read the docs.
    """
    body = ready_client.get("/sample-candidates?count=2").json()

    assert body["source"] == "synthetic"


def test_sample_candidates_is_reproducible_from_its_seed(ready_client: TestClient) -> None:
    first = ready_client.get("/sample-candidates?count=4&seed=11").json()["candidates"]
    again = ready_client.get("/sample-candidates?count=4&seed=11").json()["candidates"]
    other = ready_client.get("/sample-candidates?count=4&seed=12").json()["candidates"]

    assert first == again
    assert first != other


def test_sample_candidates_refuses_more_than_rank_accepts(ready_client: TestClient) -> None:
    """Refused here rather than at `/rank`.

    Handing a caller 600 candidates when `/rank` accepts 500 would produce a batch
    that cannot be submitted, and the failure would surface one step later than the
    mistake.
    """
    response = ready_client.get("/sample-candidates?count=100000")

    assert response.status_code == 422
    assert "MAX_RANK_BATCH" in response.json()["detail"]


def test_sample_candidates_refuses_a_count_below_one(ready_client: TestClient) -> None:
    assert ready_client.get("/sample-candidates?count=0").status_code == 422


def test_sample_candidates_works_without_the_model(unready_client: TestClient) -> None:
    """It generates text and touches nothing the model owns.

    Every scoring route is refused while the model is unverified, and this one must
    not be: a reviewer can prepare a batch while the service is still starting. If
    this ever starts returning 503, a dependency was added that does not belong.
    """
    response = unready_client.get("/sample-candidates?count=2")

    assert response.status_code == 200
    assert response.json()["count"] == 2


def test_sample_candidates_are_rankable(ready_client: TestClient) -> None:
    """The whole point: what comes out of here goes straight into `/rank`."""
    candidates = ready_client.get("/sample-candidates?count=5").json()["candidates"]

    response = ready_client.post(
        "/rank",
        json={
            "job": {
                "job_id": "j_sample",
                "required_certifications": ["security_licence"],
                "min_years_experience": 3.0,
                "shift_pattern": "night",
                "site_type": "retail",
                "driving_required": False,
            },
            "candidates": candidates,
        },
    )

    assert response.status_code == 200, response.text
    ranked = response.json()["candidates"]
    assert len(ranked) == 5
    assert [c["rank"] for c in ranked] == [1, 2, 3, 4, 5]


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
