"""Ranking dataset, metrics and inference tests.

Two failures are worth defending against above all others here.

**Group leakage.** If a posting appears in both the training and validation
splits, the model is tested on questions it studied. Nothing crashes and the
metric simply comes out higher, which is the worst possible failure mode — it
looks like success.

**Silent misalignment.** LightGBM receives group *sizes*, not group ids, and
walks the rows in order. A sizes array that disagrees with the row count
associates candidates with the wrong posting and raises nothing at all.
"""

from __future__ import annotations

import pytest

from guardmatch.data.candidates import generate_candidates
from guardmatch.data.jobs import generate_jobs
from guardmatch.data.labels import generate_hidden_factors, generate_labels
from guardmatch.data.storage import Dataset, Manifest
from guardmatch.ranking.baseline import baseline_score, baseline_scores
from guardmatch.ranking.dataset import RankingDataset, RankingSplit, build_dataset
from guardmatch.ranking.evaluate import (
    CIRCULARITY_THRESHOLD,
    Comparison,
    average_precision,
    evaluate,
    ndcg_at_k,
    reciprocal_rank,
)
from guardmatch.ranking.predict import Ranker
from guardmatch.ranking.train import predict_scores, train_model


@pytest.fixture(scope="module")
def small_dataset() -> Dataset:
    """A dataset small enough to train inside a test run."""
    candidates = generate_candidates(400, seed=7)
    jobs = generate_jobs(40, seed=7)
    hidden = generate_hidden_factors([c.candidate_id for c in candidates], 7)
    pairs = generate_labels(candidates, jobs, hidden, 7, min_per_job=30, max_per_job=40)

    return Dataset(
        candidates=candidates,
        jobs=jobs,
        pairs=pairs,
        manifest=Manifest(
            generator_version="test",
            seed=7,
            n_candidates=len(candidates),
            n_jobs=len(jobs),
            n_pairs=len(pairs),
            inject_bias=False,
            grade_counts={},
            created_at="2026-08-16T00:00:00Z",
        ),
    )


@pytest.fixture(scope="module")
def ranking_dataset(small_dataset: Dataset) -> RankingDataset:
    return build_dataset(small_dataset, seed=7)


# ---------------------------------------------------------------------------
# Dataset assembly
# ---------------------------------------------------------------------------


def test_group_sizes_match_row_count(ranking_dataset: RankingDataset) -> None:
    for split in (ranking_dataset.train, ranking_dataset.valid):
        assert sum(split.group_sizes) == len(split.features)
        assert len(split.labels) == len(split.features)
        assert len(split.candidate_ids) == len(split.features)


def test_one_job_id_per_group(ranking_dataset: RankingDataset) -> None:
    for split in (ranking_dataset.train, ranking_dataset.valid):
        assert len(split.job_ids) == len(split.group_sizes)


def test_splits_share_no_postings(ranking_dataset: RankingDataset) -> None:
    """The check that keeps the reported metric honest.

    A shared posting means the model is validated on a question it trained on,
    and the only symptom is a score that looks better than it is.
    """
    assert not set(ranking_dataset.train.job_ids) & set(ranking_dataset.valid.job_ids)


def test_split_is_by_group_not_by_row(
    small_dataset: Dataset, ranking_dataset: RankingDataset
) -> None:
    """Every pair for a posting must land in the same split."""
    valid_jobs = set(ranking_dataset.valid.job_ids)
    train_jobs = set(ranking_dataset.train.job_ids)

    for pair in small_dataset.pairs:
        assert not (pair.job_id in valid_jobs and pair.job_id in train_jobs)


def test_mismatched_group_sizes_are_rejected() -> None:
    """LightGBM would silently misalign rows; this must raise instead."""
    with pytest.raises(ValueError, match="group sizes"):
        RankingSplit(
            features=[[1.0], [2.0], [3.0]],
            labels=[1, 2, 3],
            group_sizes=[2],
            job_ids=["j_1"],
            candidate_ids=["a", "b", "c"],
        )


def test_dataset_is_reproducible(small_dataset: Dataset) -> None:
    first = build_dataset(small_dataset, seed=99)
    second = build_dataset(small_dataset, seed=99)
    assert first.train.job_ids == second.train.job_ids
    assert first.valid.job_ids == second.valid.job_ids


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def test_perfect_ordering_scores_one() -> None:
    grades = [3, 2, 1, 0]
    scores = [10.0, 5.0, 2.0, 1.0]
    assert ndcg_at_k(grades, scores, 10) == pytest.approx(1.0)


def test_reversed_ordering_scores_poorly() -> None:
    grades = [3, 2, 1, 0]
    scores = [1.0, 2.0, 5.0, 10.0]
    assert ndcg_at_k(grades, scores, 10) < 0.6


def test_group_with_no_relevant_candidates_scores_zero() -> None:
    """There is no correct ordering to find, so no credit is due."""
    assert ndcg_at_k([0, 0, 0], [3.0, 2.0, 1.0], 10) == 0.0
    assert average_precision([0, 0, 0], [3.0, 2.0, 1.0]) == 0.0
    assert reciprocal_rank([0, 0, 0], [3.0, 2.0, 1.0]) == 0.0


def test_ndcg_respects_k() -> None:
    """A strong candidate below the cutoff must not be credited."""
    grades = [0, 0, 0, 0, 0, 3]
    scores = [6.0, 5.0, 4.0, 3.0, 2.0, 1.0]
    assert ndcg_at_k(grades, scores, 5) == 0.0
    assert ndcg_at_k(grades, scores, 10) > 0.0


def test_exponential_gain_favours_strong_candidates() -> None:
    """Two grade-1 candidates must not outrank one grade-3 candidate.

    With linear gain they would, and a shortlist of marginal people would score
    as well as one that found the strong applicant.
    """
    grades = [3, 1, 1]
    strong_first = ndcg_at_k(grades, [3.0, 2.0, 1.0], 2)
    weak_first = ndcg_at_k(grades, [1.0, 3.0, 2.0], 2)
    assert strong_first > weak_first


def test_reciprocal_rank_finds_first_relevant() -> None:
    assert reciprocal_rank([0, 2, 3], [3.0, 2.0, 1.0]) == pytest.approx(0.5)
    assert reciprocal_rank([2, 0, 0], [3.0, 2.0, 1.0]) == pytest.approx(1.0)


def test_grade_one_does_not_count_as_relevant() -> None:
    """Grade 1 means "only if the shortlist is thin", which is not a hire signal."""
    assert reciprocal_rank([1, 1, 1], [3.0, 2.0, 1.0]) == 0.0


# ---------------------------------------------------------------------------
# Circularity guard
# ---------------------------------------------------------------------------


def test_high_ndcg_raises_a_circularity_warning() -> None:
    """On synthetic data a near-perfect score is a defect, not a success.

    It means the label function is recoverable from the features and the model
    reproduced our own arithmetic.
    """
    labels = [3, 2, 1, 0] * 5
    scores = [10.0, 5.0, 2.0, 1.0] * 5
    metrics = evaluate(labels, scores, [4] * 5, scorer_name="test")

    assert metrics.ndcg_at_10 > CIRCULARITY_THRESHOLD
    assert metrics.warnings
    assert "leakage" in metrics.warnings[0]


def test_realistic_ndcg_raises_no_warning() -> None:
    labels = [3, 2, 1, 0] * 5
    scores = [2.0, 5.0, 1.0, 3.0] * 5
    assert not evaluate(labels, scores, [4] * 5, scorer_name="test").warnings


# ---------------------------------------------------------------------------
# Baseline
# ---------------------------------------------------------------------------


def test_baseline_rewards_meeting_requirements() -> None:
    strong = baseline_score(
        {
            "cert_overlap_ratio": 1.0,
            "exp_gap": 2.0,
            "shift_match": 1.0,
            "missing_critical_cert": 0.0,
        }
    )
    weak = baseline_score(
        {
            "cert_overlap_ratio": 0.0,
            "exp_gap": -2.0,
            "shift_match": 0.0,
            "missing_critical_cert": 1.0,
        }
    )
    assert strong > weak


def test_baseline_treats_unknown_as_neutral() -> None:
    """Scoring unknowns as failures would make the baseline artificially harsh
    and flatter the model by comparison."""
    unknown = baseline_score(
        {
            "cert_overlap_ratio": 1.0,
            "exp_gap": None,
            "shift_match": None,
            "missing_critical_cert": 0.0,
        }
    )
    failing = baseline_score(
        {
            "cert_overlap_ratio": 1.0,
            "exp_gap": -5.0,
            "shift_match": 0.0,
            "missing_critical_cert": 0.0,
        }
    )
    assert unknown == failing  # both forgo the bonuses, neither is penalised


def test_baseline_scores_the_same_matrix_the_model_sees(
    ranking_dataset: RankingDataset,
) -> None:
    scores = baseline_scores(ranking_dataset.valid.features, ranking_dataset.feature_names)
    assert len(scores) == len(ranking_dataset.valid.features)


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


def test_marginal_improvement_does_not_count_as_beating_the_baseline() -> None:
    """Under one NDCG point is noise on a few dozen groups."""
    model = evaluate([3, 2, 1, 0], [4.0, 3.0, 2.0, 1.0], [4], scorer_name="m")
    comparison = Comparison(model=model, baseline=model)
    assert comparison.ndcg_at_10_delta == 0.0
    assert not comparison.model_beats_baseline


# ---------------------------------------------------------------------------
# End-to-end training and inference
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_model_trains_and_beats_random_ordering(ranking_dataset: RankingDataset) -> None:
    result = train_model(ranking_dataset)
    scores = predict_scores(result.booster, ranking_dataset.valid)

    assert len(scores) == len(ranking_dataset.valid.features)
    assert result.best_iteration > 0

    trained = evaluate(
        ranking_dataset.valid.labels,
        scores,
        ranking_dataset.valid.group_sizes,
        scorer_name="model",
    )
    reversed_order = evaluate(
        ranking_dataset.valid.labels,
        [-s for s in scores],
        ranking_dataset.valid.group_sizes,
        scorer_name="reversed",
    )
    assert trained.ndcg_at_10 > reversed_order.ndcg_at_10


@pytest.mark.slow
def test_ranker_orders_and_breaks_ties_deterministically(
    small_dataset: Dataset, ranking_dataset: RankingDataset
) -> None:
    """Identical candidates must not be ordered by submission order.

    Otherwise a candidate's shortlist position would depend on when their
    application happened to be uploaded.
    """
    from guardmatch.parsing.extractor import parse_cv
    from guardmatch.schemas.candidate import Candidate, ParsedProfile

    result = train_model(ranking_dataset)
    ranker = Ranker(result.booster)
    job = small_dataset.jobs[0]

    profiles = [
        parse_cv(Candidate(candidate_id=c.candidate_id, cv_text=c.cv_text))
        for c in small_dataset.candidates[:20]
    ]

    ranked = ranker.rank(profiles, job)
    assert [r.rank for r in ranked] == list(range(1, len(profiles) + 1))
    assert all(
        ranked[i].relative_ranking_score >= ranked[i + 1].relative_ranking_score
        for i in range(len(ranked) - 1)
    )

    # Two identical profiles differing only in id must order by id, not by
    # position in the input list.
    template = profiles[0]
    twin_a = ParsedProfile(**{**template.model_dump(), "candidate_id": "c_aaa"})
    twin_b = ParsedProfile(**{**template.model_dump(), "candidate_id": "c_bbb"})

    forward = ranker.rank([twin_a, twin_b], job)
    backward = ranker.rank([twin_b, twin_a], job)
    assert [r.candidate_id for r in forward] == [r.candidate_id for r in backward]


@pytest.mark.slow
def test_ranking_an_empty_list_raises(ranking_dataset: RankingDataset) -> None:
    result = train_model(ranking_dataset)
    with pytest.raises(Exception, match="empty"):
        Ranker(result.booster).rank([], generate_jobs(1, seed=1)[0])
