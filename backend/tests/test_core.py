"""Core infrastructure tests.

Configuration, logging redaction and the drift snapshot were verified by hand
when they were written, which proves they worked once and nothing about whether
they still do. These are the regression tests that were deferred at the time and
recorded as outstanding.

The redaction tests carry the most weight. Logs outlive the systems that write
them and are read by more people than the database is, so a service that logs raw
CV text has built a second, less protected copy of every applicant's personal
data.
"""

from __future__ import annotations

import pytest

from guardmatch.api.dependencies import ServiceState
from guardmatch.core.config import Settings, get_settings
from guardmatch.core.exceptions import ModelNotLoadedError
from guardmatch.core.logging import REDACTED, SENSITIVE_KEYS, redact, request_context
from guardmatch.core.metrics import (
    render_metrics,
    set_model_info,
    snapshot_feature_distributions,
)
from guardmatch.schemas.enums import CertificationCode, ShiftType, SiteType
from guardmatch.schemas.job import Job

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def test_defaults_match_the_documented_values() -> None:
    """These numbers appear in the fairness report and the model card.

    Drift between the documented threshold and the enforced one would make every
    published figure wrong.
    """
    settings = Settings()
    assert settings.fairness_top_k == 10
    assert settings.adverse_impact_threshold == 0.80
    assert settings.max_fairness_gap == 0.10
    assert settings.max_rank_batch == 500


def test_settings_are_cached() -> None:
    assert get_settings() is get_settings()


def test_model_path_is_derived() -> None:
    settings = Settings(model_version="v1.2.3")
    assert settings.model_path.name == "v1.2.3"


@pytest.mark.parametrize(
    "overrides",
    [
        {"fairness_top_k": 0},
        {"adverse_impact_threshold": 1.5},
        {"adverse_impact_threshold": 0.0},
        {"max_fairness_gap": 2.0},
        {"api_port": 0},
        {"max_rank_batch": 0},
        {"log_level": "CHATTY"},
    ],
)
def test_invalid_settings_are_rejected(overrides: dict[str, object]) -> None:
    """Validation at construction, so a bad value fails at startup.

    The alternative is a silently wrong fairness report produced weeks later.
    """
    with pytest.raises(Exception, match=r"(?i)validation|must be"):
        Settings(**overrides)  # type: ignore[arg-type]


@pytest.mark.parametrize("version", ["0.1.0", "v0.1.0/../etc", "v0.1.0\\evil", "latest"])
def test_malformed_model_version_is_rejected(version: str) -> None:
    """The version becomes a directory name, so a path separator would escape."""
    with pytest.raises(Exception, match=r"(?i)validation|model_version"):
        Settings(model_version=version)


def test_top_k_cannot_exceed_the_candidate_pool() -> None:
    """Top-k metrics on fewer than k candidates would be meaningless."""
    with pytest.raises(Exception, match=r"(?i)validation|below"):
        Settings(n_candidates=5, fairness_top_k=10)


def test_log_level_is_normalised() -> None:
    assert Settings(log_level="debug").log_level == "DEBUG"


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", sorted(SENSITIVE_KEYS))
def test_every_sensitive_key_is_redacted(key: str) -> None:
    assert redact({key: "secret"})[key] == REDACTED


def test_redaction_is_recursive() -> None:
    """Personal data usually sits inside an object rather than at the top level."""
    payload = {
        "candidate_id": "c_1",
        "profile": {"name": "A Person", "cv_text": "long text", "years": 5},
    }
    cleaned = redact(payload)

    assert cleaned["candidate_id"] == "c_1"
    assert cleaned["profile"]["name"] == REDACTED
    assert cleaned["profile"]["cv_text"] == REDACTED
    assert cleaned["profile"]["years"] == 5


def test_redaction_reaches_into_lists() -> None:
    payload = {"candidates": [{"name": "A"}, {"name": "B"}]}
    cleaned = redact(payload)
    assert [entry["name"] for entry in cleaned["candidates"]] == [REDACTED, REDACTED]


def test_redaction_is_case_insensitive() -> None:
    cleaned = redact({"CV_Text": "x", "GENDER": "y"})
    assert cleaned["CV_Text"] == REDACTED
    assert cleaned["GENDER"] == REDACTED


def test_non_sensitive_values_survive() -> None:
    """Over-redaction would make logs useless and invite disabling the layer."""
    payload = {"exp_gap": 2.0, "rank": 1, "job_id": "j_1", "score": -0.5}
    assert redact(payload) == payload


def test_redaction_does_not_mutate_the_input() -> None:
    payload = {"name": "A Person"}
    redact(payload)
    assert payload["name"] == "A Person"


# ---------------------------------------------------------------------------
# Request context
# ---------------------------------------------------------------------------


def test_request_context_binds_and_restores() -> None:
    from guardmatch.core.logging import get_request_id

    assert get_request_id() is None
    with request_context("abc") as bound:
        assert bound == "abc"
        assert get_request_id() == "abc"
    assert get_request_id() is None


def test_request_context_generates_an_id_when_none_given() -> None:
    with request_context() as bound:
        assert len(bound) == 32


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def test_drift_snapshot_ignores_missing_values() -> None:
    """Missing must not be imputed here.

    Averaging a NaN as zero would make the recorded distribution disagree with
    what the model actually saw, which defeats the point of recording it.
    """
    snapshot_feature_distributions(["a", "b"], [[2.0, 1.0], [None, 0.0], [4.0, 1.0]])
    exposition = render_metrics().decode()

    assert 'guardmatch_feature_mean{feature="a"} 3.0' in exposition


def test_drift_snapshot_handles_an_empty_batch() -> None:
    snapshot_feature_distributions(["a"], [])


def test_drift_snapshot_handles_a_single_observation() -> None:
    """stdev is undefined for one value; it must report 0 rather than raise."""
    snapshot_feature_distributions(["solo"], [[1.5]])
    assert 'guardmatch_feature_stdev{feature="solo"} 0.0' in render_metrics().decode()


def test_model_info_gauge_records_the_version() -> None:
    set_model_info("v9.9.9", loaded=True)
    exposition = render_metrics().decode()
    assert 'guardmatch_model_info{version="v9.9.9"} 1.0' in exposition
    assert "guardmatch_model_loaded 1.0" in exposition


# ---------------------------------------------------------------------------
# Service state
# ---------------------------------------------------------------------------


def test_scoring_is_refused_before_the_model_loads() -> None:
    state = ServiceState(model_version="v0.1.0", ready=False, detail="still loading")
    with pytest.raises(ModelNotLoadedError, match="still loading"):
        state.require_scoring()


def test_scoring_is_refused_when_components_are_missing() -> None:
    """`ready` alone is not enough — the components have to be present."""
    state = ServiceState(model_version="v0.1.0", ready=True, detail=None)
    with pytest.raises(ModelNotLoadedError):
        state.require_scoring()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


def test_critical_certifications_are_identified() -> None:
    """Gating certifications are treated differently from nice-to-haves."""
    job = Job(
        job_id="j_1",
        required_certifications=frozenset(
            {CertificationCode.SECURITY_LICENCE, CertificationCode.CPR}
        ),
        min_years_experience=1.0,
        shift_pattern=ShiftType.DAY,
        site_type=SiteType.RETAIL,
    )
    assert job.critical_certifications == frozenset({CertificationCode.SECURITY_LICENCE})


def test_a_job_without_a_gating_certification_has_none() -> None:
    job = Job(
        job_id="j_2",
        required_certifications=frozenset({CertificationCode.CPR}),
        min_years_experience=0.0,
        shift_pattern=ShiftType.NIGHT,
        site_type=SiteType.EVENT,
    )
    assert job.critical_certifications == frozenset()
