"""Per-feature contributions via TreeSHAP.

SHAP answers the question a ranking score cannot: not "what did this candidate
score" but "which parts of their application moved the score, and by how much".
For a tree ensemble the values are exact rather than approximate, and they are
additive — base value plus every contribution reconstructs the raw score
precisely. That additivity is asserted in the tests, because an explanation that
does not sum to the thing it explains is not an explanation.

**The contributions are additive on the raw ranking score, not on a
probability.** A contribution of +0.94 means that feature pushed the candidate
up the ordering by 0.94 on the model's internal scale. It does not mean 94%, and
it does not mean 94 percentage points of hiring likelihood. This is the single
most likely misreading of the whole system, which is why the warning appears
here, in ``reasons.py``, in the API schema and in the write-up.

The explainer is built once and reused, and values are computed for a whole
batch in one call. TreeSHAP is vectorised, so a per-candidate loop would add
latency for nothing.
"""

from __future__ import annotations

from dataclasses import dataclass

import lightgbm as lgb
import numpy as np
import shap

from guardmatch.features.registry import FEATURE_NAMES, to_vector

# Tolerance for the additivity check. Contributions are float64 sums over many
# trees, so exact equality is not achievable; anything looser than this would
# hide a genuine bug.
ADDITIVITY_TOLERANCE = 1e-6


@dataclass(frozen=True)
class Contribution:
    """One feature's signed effect on a candidate's raw score."""

    feature: str
    value: float | None
    contribution: float


@dataclass(frozen=True)
class ShapExplanation:
    """Why one candidate scored what they did."""

    base_value: float
    contributions: tuple[Contribution, ...]

    @property
    def total(self) -> float:
        """Base value plus every contribution — reconstructs the raw score."""
        return self.base_value + sum(c.contribution for c in self.contributions)

    def ranked(self) -> tuple[Contribution, ...]:
        """Contributions ordered by absolute effect, largest first."""
        return tuple(sorted(self.contributions, key=lambda c: -abs(c.contribution)))


class Explainer:
    """Computes SHAP contributions for a trained ranker."""

    def __init__(self, booster: lgb.Booster, feature_names: tuple[str, ...] = FEATURE_NAMES):
        self._booster = booster
        self._feature_names = feature_names
        # Built once. Constructing a TreeExplainer walks the whole ensemble, so
        # doing it per request would dominate the latency budget.
        self._explainer = shap.TreeExplainer(booster)

    @property
    def base_value(self) -> float:
        """The model's expected output before any feature is considered."""
        expected = self._explainer.expected_value
        if isinstance(expected, (list, np.ndarray)):
            return float(np.asarray(expected).ravel()[0])
        return float(expected)

    def explain_matrix(self, matrix: np.ndarray) -> list[ShapExplanation]:
        """Explain a batch of feature rows.

        Args:
            matrix: Rows by features, in canonical order, with NaN for unknown.

        Returns:
            One explanation per row.
        """
        values = np.asarray(self._explainer.shap_values(matrix))

        # Some SHAP versions return a trailing output axis even for a single
        # output. Collapse it rather than assuming a shape.
        if values.ndim == 3:
            values = values[..., 0]

        base = self.base_value

        explanations: list[ShapExplanation] = []
        for row_index in range(values.shape[0]):
            contributions = tuple(
                Contribution(
                    feature=name,
                    value=(
                        None
                        if np.isnan(matrix[row_index, column])
                        else float(matrix[row_index, column])
                    ),
                    contribution=float(values[row_index, column]),
                )
                for column, name in enumerate(self._feature_names)
            )
            explanations.append(ShapExplanation(base_value=base, contributions=contributions))

        return explanations

    def explain(self, features: dict[str, float | None]) -> ShapExplanation:
        """Explain a single feature mapping."""
        matrix = np.array([to_vector(features)], dtype=np.float64)
        return self.explain_matrix(matrix)[0]

    def global_importance(self, matrix: np.ndarray) -> dict[str, float]:
        """Mean absolute contribution per feature across a sample.

        Published in the model card. Global importance is what catches a feature
        being far more influential than anyone intended — which is exactly how
        `shift_match` was found to carry a third of this model's weight.
        """
        values = np.asarray(self._explainer.shap_values(matrix))
        if values.ndim == 3:
            values = values[..., 0]

        means = np.abs(values).mean(axis=0)
        return {
            name: float(means[column]) for column, name in enumerate(self._feature_names)
        }
