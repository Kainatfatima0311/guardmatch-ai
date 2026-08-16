"""Feature builder and contract tests.

Two themes run through these.

The first is that **unknown must survive as unknown**. A feature computed from a
fact the parser could not extract has to arrive at the model as ``None``, not as
a zero. Several tests exist only to pin that down, because imputing a default is
the easiest possible change to make and the hardest consequence to see.

The second is the **feature contract**. Order matters as much as membership:
LightGBM receives a positional array, so a reordered column list produces
confident, plausible, entirely wrong scores with no error anywhere.
"""

from __future__ import annotations

import pytest

from guardmatch.core.exceptions import FeatureContractError
from guardmatch.features.blocklist import PROXY_REGISTER, proxy_features
from guardmatch.features.builder import MAX_RECENCY_MONTHS, MAX_ROLE_COUNT, build_features
from guardmatch.features.registry import FEATURE_NAMES, to_matrix, to_vector, validate_against
from guardmatch.schemas.candidate import ParsedProfile
from guardmatch.schemas.enums import CertificationCode, ShiftType, SiteType
from guardmatch.schemas.job import Job


def make_job(**overrides: object) -> Job:
    """A night-shift retail posting requiring a licence and first aid."""
    defaults: dict[str, object] = {
        "job_id": "j_test",
        "required_certifications": frozenset(
            {CertificationCode.SECURITY_LICENCE, CertificationCode.FIRST_AID}
        ),
        "min_years_experience": 3.0,
        "shift_pattern": ShiftType.NIGHT,
        "site_type": SiteType.RETAIL,
        "driving_required": False,
    }
    return Job(**{**defaults, **overrides})  # type: ignore[arg-type]


def make_profile(**overrides: object) -> ParsedProfile:
    """A candidate who fully meets the default job."""
    defaults: dict[str, object] = {
        "candidate_id": "c_test",
        "years_experience": 5.0,
        "certifications": frozenset(
            {CertificationCode.SECURITY_LICENCE, CertificationCode.FIRST_AID}
        ),
        "driving_licence": True,
        "shift_availability": frozenset({ShiftType.NIGHT, ShiftType.DAY}),
        "site_experience": frozenset({SiteType.RETAIL}),
        "previous_role_count": 2,
        "months_since_last_role": 4,
    }
    return ParsedProfile(**{**defaults, **overrides})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_strong_candidate_scores_well_on_every_feature() -> None:
    features = build_features(make_profile(), make_job())

    assert features["exp_gap"] == 2.0
    assert features["licence_match"] == 1.0
    assert features["cert_overlap_ratio"] == 1.0
    assert features["cert_overlap_count"] == 2.0
    assert features["missing_critical_cert"] == 0.0
    assert features["shift_match"] == 1.0
    assert features["site_type_match"] == 1.0
    assert features["driving_required_match"] == 1.0


def test_weak_candidate_scores_poorly() -> None:
    profile = make_profile(
        years_experience=0.5,
        certifications=frozenset(),
        shift_availability=frozenset({ShiftType.DAY}),
        site_experience=frozenset({SiteType.EVENT}),
    )
    features = build_features(profile, make_job())

    assert features["exp_gap"] == -2.5
    assert features["licence_match"] == 0.0
    assert features["cert_overlap_ratio"] == 0.0
    assert features["missing_critical_cert"] == 1.0
    assert features["shift_match"] == 0.0
    assert features["site_type_match"] == 0.0


def test_features_are_pairwise_not_candidate_only() -> None:
    """The same candidate must score differently against different postings.

    If this failed, the model would be learning a global candidate ranking and
    the job-matching premise would be fiction.
    """
    profile = make_profile()
    night_retail = build_features(profile, make_job())
    day_industrial = build_features(
        profile, make_job(shift_pattern=ShiftType.DAY, site_type=SiteType.INDUSTRIAL)
    )

    assert night_retail != day_industrial
    assert night_retail["site_type_match"] == 1.0
    assert day_industrial["site_type_match"] == 0.0


# ---------------------------------------------------------------------------
# Unknown stays unknown
# ---------------------------------------------------------------------------


def test_unknown_experience_produces_none_not_zero() -> None:
    features = build_features(make_profile(years_experience=None), make_job())
    assert features["exp_gap"] is None
    assert features["exp_ratio"] is None


def test_unstated_availability_produces_none_not_mismatch() -> None:
    """An empty availability set means the CV was silent, not that the
    candidate refused the shift."""
    features = build_features(make_profile(shift_availability=frozenset()), make_job())
    assert features["shift_match"] is None


def test_missing_employment_section_produces_none_site_match() -> None:
    features = build_features(
        make_profile(previous_role_count=None, site_experience=frozenset()), make_job()
    )
    assert features["site_type_match"] is None
    assert features["role_count"] is None


def test_unknown_driving_produces_none_only_when_required() -> None:
    """When driving is not required, an unknown licence cannot cost anything."""
    not_required = build_features(make_profile(driving_licence=None), make_job())
    assert not_required["driving_required_match"] == 1.0

    required = build_features(
        make_profile(driving_licence=None), make_job(driving_required=True)
    )
    assert required["driving_required_match"] is None


def test_stated_no_driving_is_zero_not_none() -> None:
    """False and None must stay distinct all the way to the model."""
    features = build_features(
        make_profile(driving_licence=False), make_job(driving_required=True)
    )
    assert features["driving_required_match"] == 0.0


def test_explicit_zero_roles_is_zero_not_none() -> None:
    features = build_features(make_profile(previous_role_count=0), make_job())
    assert features["role_count"] == 0.0


# ---------------------------------------------------------------------------
# Proxy mitigations
# ---------------------------------------------------------------------------


def test_role_count_is_capped() -> None:
    """Capping flattens the tail where the age signal is strongest."""
    features = build_features(make_profile(previous_role_count=50), make_job())
    assert features["role_count"] == float(MAX_ROLE_COUNT)


def test_recency_is_capped() -> None:
    features = build_features(make_profile(months_since_last_role=999), make_job())
    assert features["recency_months"] == float(MAX_RECENCY_MONTHS)


def test_every_registered_proxy_is_a_real_feature() -> None:
    """A register naming features that do not exist is documentation theatre."""
    assert proxy_features() <= set(FEATURE_NAMES)
    assert len(PROXY_REGISTER) >= 4
    for risk in PROXY_REGISTER:
        assert risk.leaks and risk.mitigation


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_job_with_no_requirements_gives_full_overlap() -> None:
    features = build_features(
        make_profile(), make_job(required_certifications=frozenset())
    )
    assert features["cert_overlap_ratio"] == 1.0
    assert features["licence_match"] == 1.0


def test_zero_minimum_experience_does_not_divide_by_zero() -> None:
    features = build_features(make_profile(), make_job(min_years_experience=0.0))
    assert features["exp_ratio"] is not None
    assert features["exp_gap"] == 5.0


def test_extra_certifications_are_counted() -> None:
    profile = make_profile(
        certifications=frozenset(
            {
                CertificationCode.SECURITY_LICENCE,
                CertificationCode.FIRST_AID,
                CertificationCode.CPR,
                CertificationCode.DOG_HANDLING,
            }
        )
    )
    assert build_features(profile, make_job())["extra_cert_count"] == 2.0


# ---------------------------------------------------------------------------
# Feature contract
# ---------------------------------------------------------------------------


def test_builder_output_matches_the_contract_exactly() -> None:
    features = build_features(make_profile(), make_job())
    assert set(features) == set(FEATURE_NAMES)


def test_vector_follows_canonical_order() -> None:
    features = build_features(make_profile(), make_job())
    vector = to_vector(features)
    assert len(vector) == len(FEATURE_NAMES)
    assert vector[FEATURE_NAMES.index("licence_match")] == features["licence_match"]


def test_matrix_preserves_row_order() -> None:
    rows = [
        build_features(make_profile(years_experience=1.0), make_job()),
        build_features(make_profile(years_experience=9.0), make_job()),
    ]
    matrix = to_matrix(rows)
    gap_index = FEATURE_NAMES.index("exp_gap")
    assert matrix[0][gap_index] == -2.0
    assert matrix[1][gap_index] == 6.0


def test_missing_feature_is_rejected() -> None:
    features = build_features(make_profile(), make_job())
    del features["shift_match"]
    with pytest.raises(FeatureContractError, match="missing"):
        to_vector(features)


def test_unexpected_feature_is_rejected() -> None:
    features = build_features(make_profile(), make_job())
    features["some_new_idea"] = 1.0
    with pytest.raises(FeatureContractError, match="unexpected"):
        to_vector(features)


def test_reordered_contract_is_rejected() -> None:
    """Reordering is as damaging as a missing column and far less visible."""
    reordered = (FEATURE_NAMES[1], FEATURE_NAMES[0], *FEATURE_NAMES[2:])
    with pytest.raises(FeatureContractError, match="ORDER"):
        validate_against(reordered)


def test_changed_contract_membership_is_rejected() -> None:
    with pytest.raises(FeatureContractError, match="SET"):
        validate_against([*FEATURE_NAMES[:-1], "something_else"])


def test_matching_contract_passes() -> None:
    validate_against(FEATURE_NAMES)
