"""Serving-side ranking.

The only place scores are turned into an ordering. Two rules are enforced here
rather than left to callers.

**Scores are relative, and the type says so.** A LambdaRank output is not a
probability and is not comparable across postings. The field is named
``relative_ranking_score`` and the ordering is what the caller is meant to use.
Reading a ranking score as "87% likely to be hired" is the most plausible way
this system gets misused, so the contract is shaped to make that reading
awkward.

**Ties are broken deterministically.** Two candidates with identical features
score identically, and Python's sort would then order them by whichever arrived
first — meaning position in a shortlist would depend on upload order. Ties are
broken by candidate id instead, so the same request always produces the same
ranking.
"""

from __future__ import annotations

from dataclasses import dataclass

import lightgbm as lgb
import numpy as np

from guardmatch.core.exceptions import ModelNotLoadedError
from guardmatch.core.metrics import observe_scores, snapshot_feature_distributions
from guardmatch.features.builder import build_features
from guardmatch.features.registry import FEATURE_NAMES, to_vector
from guardmatch.schemas.candidate import ParsedProfile
from guardmatch.schemas.job import Job


@dataclass(frozen=True)
class RankedCandidate:
    """One candidate's position for one posting."""

    candidate_id: str
    rank: int
    relative_ranking_score: float
    features: dict[str, float | None]


class Ranker:
    """Scores and orders candidates for a single job posting."""

    def __init__(self, booster: lgb.Booster, feature_names: tuple[str, ...] = FEATURE_NAMES):
        self._booster = booster
        self._feature_names = feature_names

    @property
    def feature_names(self) -> tuple[str, ...]:
        return self._feature_names

    def score(self, profile: ParsedProfile, job: Job) -> tuple[float, dict[str, float | None]]:
        """Score one candidate against one job.

        Returns the raw relative score and the features it was computed from.
        The features come back because the explainer needs exactly the values
        the model saw — recomputing them elsewhere risks the two drifting apart.
        """
        features = build_features(profile, job)
        matrix = np.array([to_vector(features)], dtype=np.float64)
        raw = self._booster.predict(matrix, num_iteration=self._booster.best_iteration)
        return float(np.asarray(raw).ravel()[0]), features

    def rank(self, profiles: list[ParsedProfile], job: Job) -> list[RankedCandidate]:
        """Order candidates for one posting, best fit first.

        Args:
            profiles: Parsed candidates competing for this posting.
            job: The posting.

        Returns:
            Candidates ordered by score, each carrying its rank and the features
            behind it.

        Raises:
            ModelNotLoadedError: No candidates were supplied.
        """
        if not profiles:
            msg = "cannot rank an empty candidate list"
            raise ModelNotLoadedError(msg)

        feature_rows = [build_features(profile, job) for profile in profiles]
        matrix = np.array([to_vector(row) for row in feature_rows], dtype=np.float64)

        raw = self._booster.predict(matrix, num_iteration=self._booster.best_iteration)
        scores = [float(value) for value in np.asarray(raw).ravel()]

        observe_scores(scores)
        snapshot_feature_distributions(
            list(self._feature_names), [to_vector(row) for row in feature_rows]
        )

        # Descending by score, then ascending by candidate id. The tiebreak keeps
        # the ordering independent of the order candidates were submitted in.
        order = sorted(
            range(len(profiles)),
            key=lambda index: (-scores[index], profiles[index].candidate_id),
        )

        return [
            RankedCandidate(
                candidate_id=profiles[index].candidate_id,
                rank=position,
                relative_ranking_score=scores[index],
                features=feature_rows[index],
            )
            for position, index in enumerate(order, start=1)
        ]
