"""Training the LambdaRank model.

LightGBM's ``lambdarank`` objective optimises NDCG directly. It considers all
candidates for a posting together and learns which orderings score well, which
is the actual task — HR does not need a calibrated probability per candidate,
they need the right people at the top of the list.

The hyperparameter grid is deliberately small. With roughly 150 training groups,
an extensive search would fit the validation set rather than the problem, and
the reported score would be an artefact of the search itself.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any

import lightgbm as lgb
import numpy as np

from guardmatch.core.logging import get_logger
from guardmatch.ranking.dataset import RankingDataset, RankingSplit

logger = get_logger(__name__)

# Fixed across every run so training is reproducible.
SEED = 42

# Small on purpose. Each entry is a plausible setting rather than a point on a
# fine sweep.
HYPERPARAMETER_GRID: dict[str, list[Any]] = {
    "num_leaves": [7, 15, 31],
    "learning_rate": [0.05, 0.1],
    "min_data_in_leaf": [20, 50],
}

_BASE_PARAMS: dict[str, Any] = {
    "objective": "lambdarank",
    "metric": "ndcg",
    "ndcg_eval_at": [5, 10],
    # Truncation caps how deep into each list the gradient looks. Set to the
    # shortlist depth: ordering positions nobody will ever read is wasted
    # capacity.
    "lambdarank_truncation_level": 10,
    "boosting_type": "gbdt",
    "feature_fraction": 0.9,
    "bagging_fraction": 0.9,
    "bagging_freq": 1,
    "seed": SEED,
    "deterministic": True,
    "force_row_wise": True,
    "verbosity": -1,
}

MAX_ROUNDS = 500
EARLY_STOPPING_ROUNDS = 50


@dataclass(frozen=True)
class TrainingResult:
    """A trained booster with the settings that produced it."""

    booster: lgb.Booster
    params: dict[str, Any]
    best_iteration: int
    best_validation_ndcg: float
    grid_size: int
    trials: tuple[dict[str, Any], ...] = field(default_factory=tuple)


def to_matrix(split: RankingSplit) -> np.ndarray[Any, Any]:
    """Convert a split's feature rows into a float array.

    ``None`` becomes ``NaN``, which LightGBM treats as genuinely missing and
    routes down whichever branch the data supports. This is the whole reason
    unknown values were never imputed upstream.
    """
    return np.array(split.features, dtype=np.float64)


def _to_lgb_dataset(split: RankingSplit, reference: lgb.Dataset | None = None) -> lgb.Dataset:
    return lgb.Dataset(
        to_matrix(split),
        label=np.array(split.labels, dtype=np.int32),
        group=np.array(split.group_sizes, dtype=np.int32),
        reference=reference,
        free_raw_data=False,
    )


def train_model(dataset: RankingDataset) -> TrainingResult:
    """Train LambdaRank, selecting hyperparameters by validation NDCG@10.

    Args:
        dataset: Train and validation splits, already grouped by posting.

    Returns:
        The best booster found, with the settings and score that selected it.
    """
    train_set = _to_lgb_dataset(dataset.train)
    valid_set = _to_lgb_dataset(dataset.valid, reference=train_set)

    keys = list(HYPERPARAMETER_GRID)
    combinations = list(itertools.product(*(HYPERPARAMETER_GRID[key] for key in keys)))

    best: TrainingResult | None = None
    trials: list[dict[str, Any]] = []

    logger.info(
        "training_started",
        grid_size=len(combinations),
        train_groups=dataset.train.n_groups,
        valid_groups=dataset.valid.n_groups,
    )

    for combination in combinations:
        params = {**_BASE_PARAMS, **dict(zip(keys, combination, strict=True))}

        booster = lgb.train(
            params,
            train_set,
            num_boost_round=MAX_ROUNDS,
            valid_sets=[valid_set],
            valid_names=["valid"],
            callbacks=[
                lgb.early_stopping(EARLY_STOPPING_ROUNDS, verbose=False),
                lgb.log_evaluation(period=0),
            ],
        )

        score = float(booster.best_score["valid"]["ndcg@10"])
        trials.append({**dict(zip(keys, combination, strict=True)), "ndcg_at_10": score})

        if best is None or score > best.best_validation_ndcg:
            best = TrainingResult(
                booster=booster,
                params=params,
                best_iteration=booster.best_iteration,
                best_validation_ndcg=score,
                grid_size=len(combinations),
            )

    if best is None:  # pragma: no cover - grid is never empty
        msg = "hyperparameter grid produced no models"
        raise RuntimeError(msg)

    logger.info(
        "training_complete",
        best_ndcg_at_10=round(best.best_validation_ndcg, 4),
        best_iteration=best.best_iteration,
        num_leaves=best.params["num_leaves"],
        learning_rate=best.params["learning_rate"],
        min_data_in_leaf=best.params["min_data_in_leaf"],
    )

    return TrainingResult(
        booster=best.booster,
        params=best.params,
        best_iteration=best.best_iteration,
        best_validation_ndcg=best.best_validation_ndcg,
        grid_size=best.grid_size,
        trials=tuple(trials),
    )


def predict_scores(booster: lgb.Booster, split: RankingSplit) -> list[float]:
    """Score every row in a split."""
    raw = booster.predict(to_matrix(split), num_iteration=booster.best_iteration)
    return [float(value) for value in np.asarray(raw).ravel()]
