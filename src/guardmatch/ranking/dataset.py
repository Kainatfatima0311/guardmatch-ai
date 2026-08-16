"""Assembling labelled pairs into LightGBM ranking input.

Ranking data has a shape that ordinary tabular data does not: rows belong to
**query groups**, one per job posting, and the model learns an ordering *within*
each group rather than an absolute score across all of them.

Two details decide whether the resulting numbers mean anything.

**Rows must be contiguous by group.** LightGBM does not receive group ids — it
receives a list of group *sizes* and walks the rows in order. Rows out of order
silently associate candidates with the wrong posting, and nothing raises.

**The split must be at the group level.** Splitting rows would place some
candidates for a posting in training and others in validation, letting the model
memorise that posting's particular requirements and then be tested on it. The
reported NDCG would be optimistic and wrong, in a way no amount of staring at
the number would reveal.
"""

from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass

from guardmatch.core.logging import get_logger
from guardmatch.data.storage import Dataset
from guardmatch.features.builder import build_features
from guardmatch.features.registry import FEATURE_NAMES, to_vector
from guardmatch.parsing.extractor import parse_cv
from guardmatch.schemas.candidate import Candidate, ParsedProfile
from guardmatch.schemas.job import Job

logger = get_logger(__name__)


@dataclass(frozen=True)
class RankingSplit:
    """One half of a group-level split, in LightGBM's expected layout."""

    features: list[list[float | None]]
    labels: list[int]
    group_sizes: list[int]
    job_ids: list[str]
    candidate_ids: list[str]

    def __post_init__(self) -> None:
        if sum(self.group_sizes) != len(self.features):
            msg = (
                f"group sizes sum to {sum(self.group_sizes)} but there are "
                f"{len(self.features)} rows; LightGBM would associate candidates with the "
                f"wrong postings"
            )
            raise ValueError(msg)
        if len(self.group_sizes) != len(self.job_ids):
            msg = "one job id is required per group"
            raise ValueError(msg)

    @property
    def n_groups(self) -> int:
        return len(self.group_sizes)


@dataclass(frozen=True)
class RankingDataset:
    """Train and validation splits, sharing one feature contract."""

    train: RankingSplit
    valid: RankingSplit
    feature_names: tuple[str, ...] = FEATURE_NAMES


def parse_all(dataset: Dataset) -> dict[str, ParsedProfile]:
    """Parse every candidate's CV once, keyed by candidate id.

    Parsing is the expensive step and each candidate appears in several postings,
    so this is cached rather than repeated per pair.
    """
    profiles: dict[str, ParsedProfile] = {}
    for candidate in dataset.candidates:
        profiles[candidate.candidate_id] = parse_cv(
            Candidate(candidate_id=candidate.candidate_id, cv_text=candidate.cv_text)
        )
    return profiles


def _build_split(
    job_ids: list[str],
    jobs_by_id: dict[str, Job],
    pairs_by_job: dict[str, list[tuple[str, int]]],
    profiles: dict[str, ParsedProfile],
) -> RankingSplit:
    """Build one split, keeping rows contiguous within each group."""
    features: list[list[float | None]] = []
    labels: list[int] = []
    group_sizes: list[int] = []
    candidate_ids: list[str] = []
    kept_job_ids: list[str] = []

    for job_id in job_ids:
        entries = pairs_by_job[job_id]
        if not entries:
            continue

        job = jobs_by_id[job_id]
        for candidate_id, grade in entries:
            features.append(to_vector(build_features(profiles[candidate_id], job)))
            labels.append(grade)
            candidate_ids.append(candidate_id)

        group_sizes.append(len(entries))
        kept_job_ids.append(job_id)

    return RankingSplit(
        features=features,
        labels=labels,
        group_sizes=group_sizes,
        job_ids=kept_job_ids,
        candidate_ids=candidate_ids,
    )


def build_dataset(
    dataset: Dataset,
    *,
    seed: int,
    valid_fraction: float = 0.25,
    profiles: dict[str, ParsedProfile] | None = None,
) -> RankingDataset:
    """Turn a generated dataset into train and validation ranking splits.

    Args:
        dataset: Candidates, jobs and labelled pairs.
        seed: Seed for the group-level shuffle.
        valid_fraction: Share of **postings** held out, not share of rows.
        profiles: Pre-parsed profiles, to avoid re-parsing across calls.

    Returns:
        Train and validation splits with contiguous groups and no posting
        appearing in both.
    """
    resolved_profiles = profiles if profiles is not None else parse_all(dataset)
    jobs_by_id = {job.job_id: job for job in dataset.jobs}

    pairs_by_job: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for pair in dataset.pairs:
        pairs_by_job[pair.job_id].append((pair.candidate_id, pair.grade))

    # Shuffle postings, not rows. This is the line that keeps the evaluation
    # honest.
    job_ids = sorted(pairs_by_job)
    random.Random(seed).shuffle(job_ids)

    split_at = int(len(job_ids) * (1.0 - valid_fraction))
    train_jobs, valid_jobs = job_ids[:split_at], job_ids[split_at:]

    overlap = set(train_jobs) & set(valid_jobs)
    if overlap:  # pragma: no cover - defensive
        msg = f"postings appear in both splits: {sorted(overlap)[:5]}"
        raise ValueError(msg)

    train = _build_split(train_jobs, jobs_by_id, pairs_by_job, resolved_profiles)
    valid = _build_split(valid_jobs, jobs_by_id, pairs_by_job, resolved_profiles)

    logger.info(
        "ranking_dataset_built",
        train_groups=train.n_groups,
        train_rows=len(train.features),
        valid_groups=valid.n_groups,
        valid_rows=len(valid.features),
        features=len(FEATURE_NAMES),
    )

    return RankingDataset(train=train, valid=valid)
