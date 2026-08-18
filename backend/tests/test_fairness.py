"""Fairness gate — the model must not discriminate by the project's own standard.

**This file is a build gate.** A failure here means the model disadvantages a
protected group beyond the threshold this project committed to, and CI must
fail. The correct response is to fix the model, never to relax the threshold.

Beyond the gate itself, two things are proven here.

**The exposure metric earns its place.** A test constructs a case where two
groups are shortlisted at exactly equal rates but one is consistently placed
lower within the shortlist. Every classification-style fairness metric passes
that case; only exposure catches it. Without that test, the ranking-specific
metric is an untested claim.

**The audit detects a known bias.** The generator can inject a correlation
between gender and night availability, which reaches the model through the
entirely neutral-looking `shift_match` feature. If the audit cannot find a bias
we deliberately planted, it cannot be trusted to find one we did not.
"""

from __future__ import annotations

import pytest

from guardmatch.core.config import Settings
from guardmatch.data.candidates import generate_candidates
from guardmatch.data.jobs import generate_jobs
from guardmatch.data.labels import generate_hidden_factors, generate_labels
from guardmatch.data.protected import generate_protected_attributes
from guardmatch.data.storage import Dataset, Manifest
from guardmatch.fairness.audit import rank_validation_groups, run_audit
from guardmatch.fairness.metrics import (
    QUALIFIED_GRADE,
    RankedGroup,
    audit_attribute,
    position_exposure,
)
from guardmatch.ranking.dataset import RankingDataset, build_dataset
from guardmatch.ranking.train import train_model

pytestmark = pytest.mark.gate

THRESHOLDS = {
    "top_k": 10,
    "min_group_size": 30,
    "adverse_impact_threshold": 0.80,
    "max_gap": 0.10,
}


def build_posting(job_id: str, ordering: list[tuple[str, int]]) -> RankedGroup:
    """A posting whose candidates are already in ranked order."""
    return RankedGroup(
        job_id=job_id,
        candidate_ids=[candidate for candidate, _ in ordering],
        grades=[grade for _, grade in ordering],
    )


# ---------------------------------------------------------------------------
# Exposure
# ---------------------------------------------------------------------------


def test_exposure_decreases_with_rank() -> None:
    """Rank 1 must be worth materially more than rank 10."""
    assert position_exposure(1) > position_exposure(2) > position_exposure(10)
    assert position_exposure(1) / position_exposure(10) > 2.0


def test_exposure_catches_equal_selection_but_lower_placement() -> None:
    """The case that justifies a ranking-specific metric.

    Both groups reach the top-10 at identical rates, so selection-based metrics
    see perfect fairness. But one group is placed at positions 1-5 and the other
    at 6-10 in every single posting, which is a real and systematic harm.
    """
    postings = [
        build_posting(
            f"j_{index}",
            [(f"a_{index}_{i}", 3) for i in range(5)] + [(f"b_{index}_{i}", 3) for i in range(5)],
        )
        for index in range(20)
    ]

    group_of = {
        candidate: ("group_a" if candidate.startswith("a_") else "group_b")
        for posting in postings
        for candidate in posting.candidate_ids
    }

    audit = audit_attribute("test", postings, group_of, **THRESHOLDS)  # type: ignore[arg-type]

    # Selection-based metrics see nothing wrong: everyone is in the top 10.
    assert audit.adverse_impact_ratio == pytest.approx(1.0)
    assert audit.demographic_parity_gap == pytest.approx(0.0)

    # Exposure sees the difference, and fails.
    assert audit.exposure_ratio is not None
    assert audit.exposure_ratio < 0.80
    assert not audit.passes
    assert any("exposure" in failure for failure in audit.failures)


# ---------------------------------------------------------------------------
# Adverse impact
# ---------------------------------------------------------------------------


def test_equal_treatment_passes_every_metric() -> None:
    """Alternating placement gives both groups the same rates and positions."""
    postings = []
    for index in range(20):
        ordering: list[tuple[str, int]] = []
        for position in range(20):
            prefix = "a" if position % 2 == 0 else "b"
            ordering.append((f"{prefix}_{index}_{position}", 3 if position < 10 else 0))
        postings.append(build_posting(f"j_{index}", ordering))

    group_of = {
        candidate: ("group_a" if candidate.startswith("a_") else "group_b")
        for posting in postings
        for candidate in posting.candidate_ids
    }

    audit = audit_attribute("test", postings, group_of, **THRESHOLDS)  # type: ignore[arg-type]

    assert audit.passes
    assert audit.adverse_impact_ratio is not None
    assert audit.adverse_impact_ratio > 0.9


def test_four_fifths_breach_is_detected() -> None:
    """One group almost never reaches the shortlist."""
    postings = []
    for index in range(20):
        ordering = [(f"a_{index}_{i}", 3) for i in range(9)]
        ordering.append((f"b_{index}_0", 3))
        ordering.extend((f"b_{index}_{i}", 0) for i in range(1, 10))
        postings.append(build_posting(f"j_{index}", ordering))

    group_of = {
        candidate: ("group_a" if candidate.startswith("a_") else "group_b")
        for posting in postings
        for candidate in posting.candidate_ids
    }

    audit = audit_attribute("test", postings, group_of, **THRESHOLDS)  # type: ignore[arg-type]

    assert audit.adverse_impact_ratio is not None
    assert audit.adverse_impact_ratio < 0.80
    assert not audit.passes
    assert any("adverse impact" in failure for failure in audit.failures)


# ---------------------------------------------------------------------------
# Equal opportunity
# ---------------------------------------------------------------------------


def test_equal_opportunity_separates_unfairness_from_qualification() -> None:
    """Groups can differ in qualification without the model being unfair.

    Here group B has fewer qualified candidates, so its overall selection rate is
    lower — but every qualified candidate from both groups is shortlisted.
    Conflating the two would blame the model for a difference in the applicant
    pool.
    """
    postings = []
    for index in range(20):
        ordering: list[tuple[str, int]] = []
        ordering.extend((f"a_{index}_{i}", 3) for i in range(5))
        ordering.extend((f"b_{index}_{i}", 3) for i in range(5))
        ordering.extend((f"a_{index}_x{i}", 0) for i in range(5))
        ordering.extend((f"b_{index}_x{i}", 0) for i in range(5))
        postings.append(build_posting(f"j_{index}", ordering))

    group_of = {
        candidate: ("group_a" if candidate.startswith("a_") else "group_b")
        for posting in postings
        for candidate in posting.candidate_ids
    }

    audit = audit_attribute("test", postings, group_of, **THRESHOLDS)  # type: ignore[arg-type]

    assert audit.equal_opportunity_gap == pytest.approx(0.0, abs=1e-9)
    for group in audit.groups:
        assert group.qualified_selection_rate == pytest.approx(1.0)


def test_qualified_threshold_excludes_marginal_candidates() -> None:
    """Grade 1 means "only if the shortlist is thin", not "would hire"."""
    assert QUALIFIED_GRADE == 2


# ---------------------------------------------------------------------------
# Small groups
# ---------------------------------------------------------------------------


def test_small_groups_are_suppressed_not_reported() -> None:
    """A rate computed from a handful of people is noise, not a finding."""
    postings = []
    for index in range(20):
        ordering = [(f"a_{index}_{i}", 3 if i < 10 else 0) for i in range(20)]
        if index == 0:
            ordering.append(("rare_0", 3))
        postings.append(build_posting(f"j_{index}", ordering))

    group_of = {
        candidate: ("rare" if candidate.startswith("rare") else "common")
        for posting in postings
        for candidate in posting.candidate_ids
    }

    audit = audit_attribute("test", postings, group_of, **THRESHOLDS)  # type: ignore[arg-type]

    assert "rare" in audit.suppressed_groups
    assert [group.group for group in audit.groups] == ["common"]


def test_a_single_comparable_group_is_not_a_pass() -> None:
    """With nothing to compare against, reporting a pass would imply a check
    that never ran."""
    postings = [
        build_posting(f"j_{index}", [(f"a_{index}_{i}", 3 if i < 10 else 0) for i in range(20)])
        for index in range(20)
    ]
    group_of = dict.fromkeys(
        (candidate for posting in postings for candidate in posting.candidate_ids), "only_group"
    )

    audit = audit_attribute("test", postings, group_of, **THRESHOLDS)  # type: ignore[arg-type]

    assert not audit.passes
    assert any("fewer than two groups" in failure for failure in audit.failures)


def test_unmapped_candidates_are_skipped_not_counted() -> None:
    """A candidate with no recorded demographics must not distort any group.

    Sized so both mapped groups clear `min_group_size`; otherwise suppression
    would empty the result and the test would pass for the wrong reason.
    """
    postings = [
        build_posting(f"j_{index}", [(f"c_{index}_{i}", 3 if i < 10 else 0) for i in range(50)])
        for index in range(4)
    ]

    # Map only the first 40 of each posting, leaving 10 per posting unmapped.
    group_of = {
        f"c_{index}_{i}": ("group_a" if i % 2 == 0 else "group_b")
        for index in range(4)
        for i in range(40)
    }

    audit = audit_attribute("test", postings, group_of, **THRESHOLDS)  # type: ignore[arg-type]

    assert sum(group.n_appearances for group in audit.groups) == 160
    assert {group.group for group in audit.groups} == {"group_a", "group_b"}


# ---------------------------------------------------------------------------
# End to end, against a real model
# ---------------------------------------------------------------------------


# Strength used for the gate demonstration.
#
# Strength 1.0 is the realistic setting — a night-availability gap of roughly
# 0.40, which is what a caring-responsibilities correlation actually looks like.
# It produces an adverse impact ratio hovering around 0.80, sometimes just below
# and sometimes just above, depending on the sample. That borderline behaviour is
# an honest finding about the four-fifths threshold's sensitivity to proxy bias,
# but it makes for an unreliable test: a gate demonstration that passes on some
# seeds proves nothing.
#
# 2.0 produces a ratio near 0.70 with p ≈ 0.001, detected on every seed tried.
# Both figures are reported in the fairness write-up.
GATE_BIAS_STRENGTH = 2.0


def build_case(
    *, inject_bias: bool, bias_strength: float = GATE_BIAS_STRENGTH
) -> tuple[RankingDataset, dict[str, object]]:
    """Train-ready data plus demographics, with bias optionally injected."""
    seed = 21
    candidates = generate_candidates(900, seed=seed)
    jobs = generate_jobs(60, seed=seed)
    hidden = generate_hidden_factors([c.candidate_id for c in candidates], seed)
    pairs = generate_labels(candidates, jobs, hidden, seed, min_per_job=40, max_per_job=60)

    dataset = Dataset(
        candidates=candidates,
        jobs=jobs,
        pairs=pairs,
        manifest=Manifest(
            generator_version="test",
            seed=seed,
            n_candidates=len(candidates),
            n_jobs=len(jobs),
            n_pairs=len(pairs),
            inject_bias=inject_bias,
            grade_counts={},
            created_at="2026-08-17T00:00:00Z",
        ),
    )

    protected = generate_protected_attributes(
        candidates, seed, inject_bias=inject_bias, bias_strength=bias_strength
    )
    return build_dataset(dataset, seed=seed), protected  # type: ignore[return-value]


@pytest.mark.slow
def test_unbiased_data_passes_the_audit() -> None:
    """The gate must not fire on clean data.

    Asserted as its own test because a gate that fails on everything is as
    useless as one that fails on nothing — and far more likely to be switched
    off.
    """
    ranking_dataset, protected = build_case(inject_bias=False)
    result = train_model(ranking_dataset)

    report = run_audit(
        result.booster,
        ranking_dataset,
        protected,  # type: ignore[arg-type]
        model_version="v-test-clean",
        settings=Settings(),
    )

    gender = next(a for a in report.attributes if a.attribute == "gender")
    assert gender.passes, f"clean data failed the audit: {gender.failures}"


@pytest.mark.slow
def test_audit_detects_the_injected_bias() -> None:
    """The gate's own proof of life.

    The generator plants a correlation between gender and night availability,
    which reaches the model through `shift_match` — a legitimate, job-relevant,
    entirely neutral-looking feature. If the audit cannot find a bias we planted
    ourselves, it cannot be trusted to find one we did not.
    """
    ranking_dataset, protected = build_case(inject_bias=True)
    result = train_model(ranking_dataset)

    report = run_audit(
        result.booster,
        ranking_dataset,
        protected,  # type: ignore[arg-type]
        model_version="v-test-biased",
        settings=Settings(),
    )

    gender = next(a for a in report.attributes if a.attribute == "gender")

    assert gender.adverse_impact_ratio is not None
    assert not gender.passes, (
        "the audit failed to detect a deliberately injected bias — "
        "the fairness suite cannot be trusted"
    )


@pytest.mark.slow
def test_audit_reports_every_attribute_even_when_one_fails() -> None:
    """A breach must not hide the other findings behind it.

    Aborting on the first failure would withhold exactly the information needed
    to decide what to do about it.
    """
    ranking_dataset, protected = build_case(inject_bias=True)
    result = train_model(ranking_dataset)

    report = run_audit(
        result.booster,
        ranking_dataset,
        protected,  # type: ignore[arg-type]
        model_version="v-test-biased",
        settings=Settings(),
    )

    assert {a.attribute for a in report.attributes} == {"gender", "age_band", "nationality"}
    assert report.n_postings > 0
    assert report.n_rows > 0


@pytest.mark.slow
def test_ranked_groups_match_the_validation_split() -> None:
    """The audit must measure the ordering the service would actually produce."""
    ranking_dataset, _ = build_case(inject_bias=False)
    result = train_model(ranking_dataset)

    ranked = rank_validation_groups(result.booster, ranking_dataset)

    assert len(ranked) == ranking_dataset.valid.n_groups
    assert [len(group.candidate_ids) for group in ranked] == ranking_dataset.valid.group_sizes
