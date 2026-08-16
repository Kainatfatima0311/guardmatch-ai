"""Ranking metrics, computed per query group.

Every metric here is calculated within one posting and then averaged across
postings. Pooling all rows together would compare candidates who were never in
competition with each other, which is not the question the system answers.

The circularity check is the important part of this module. On synthetic data an
unusually high score is not good news — it means the label function leaked
through the features and the model reproduced our own arithmetic. So a strong
NDCG raises a warning rather than being reported as success, which is the
opposite of the normal reflex and the reason it has to be automated.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from guardmatch.core.logging import get_logger

logger = get_logger(__name__)

# Above this, a result is treated as evidence of label leakage rather than of
# model quality. See docs/data-card.md section 4.
CIRCULARITY_THRESHOLD = 0.95

# Grade at or above which a candidate counts as genuinely relevant, used by the
# binary metrics. Grade 2 is "would interview"; grade 1 is "only if the
# shortlist is thin", which is not a hiring signal.
RELEVANT_GRADE = 2


@dataclass(frozen=True)
class RankingMetrics:
    """Ranking quality for one scorer on one split."""

    ndcg_at_5: float
    ndcg_at_10: float
    mean_average_precision: float
    mean_reciprocal_rank: float
    n_groups: int
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, float]:
        """Flat mapping for metrics.json."""
        return {
            "ndcg_at_5": self.ndcg_at_5,
            "ndcg_at_10": self.ndcg_at_10,
            "mean_average_precision": self.mean_average_precision,
            "mean_reciprocal_rank": self.mean_reciprocal_rank,
            "n_groups": float(self.n_groups),
        }


def _dcg(grades: list[int], k: int) -> float:
    """Discounted cumulative gain over the first ``k`` positions.

    Uses the exponential gain form, which weights a grade-3 candidate far above
    a grade-1 one. With linear gain, filling a shortlist with marginal
    candidates would score almost as well as finding the strong ones.
    """
    return float(
        sum(
            (2**grade - 1) / math.log2(position + 2)
            for position, grade in enumerate(grades[:k])
        )
    )


def ndcg_at_k(grades: list[int], scores: list[float], k: int) -> float:
    """NDCG for one query group.

    Returns 0.0 when a group contains no relevant candidates at all — there is
    no correct ordering to find, so crediting the model would be meaningless.
    """
    ranked = [grade for _, grade in sorted(zip(scores, grades, strict=True), key=lambda p: -p[0])]
    ideal = sorted(grades, reverse=True)

    ideal_dcg = _dcg(ideal, k)
    if ideal_dcg == 0.0:
        return 0.0
    return _dcg(ranked, k) / ideal_dcg


def average_precision(grades: list[int], scores: list[float]) -> float:
    """Average precision for one group, treating grade >= 2 as relevant."""
    ranked = [grade for _, grade in sorted(zip(scores, grades, strict=True), key=lambda p: -p[0])]
    relevant_total = sum(1 for grade in grades if grade >= RELEVANT_GRADE)
    if relevant_total == 0:
        return 0.0

    hits = 0
    precision_sum = 0.0
    for position, grade in enumerate(ranked, start=1):
        if grade >= RELEVANT_GRADE:
            hits += 1
            precision_sum += hits / position

    return precision_sum / relevant_total


def reciprocal_rank(grades: list[int], scores: list[float]) -> float:
    """Reciprocal rank of the first genuinely relevant candidate."""
    ranked = [grade for _, grade in sorted(zip(scores, grades, strict=True), key=lambda p: -p[0])]
    for position, grade in enumerate(ranked, start=1):
        if grade >= RELEVANT_GRADE:
            return 1.0 / position
    return 0.0


def _iter_groups(
    labels: list[int], scores: list[float], group_sizes: list[int]
) -> list[tuple[list[int], list[float]]]:
    """Slice flat arrays back into per-group pairs."""
    groups: list[tuple[list[int], list[float]]] = []
    offset = 0
    for size in group_sizes:
        groups.append((labels[offset : offset + size], scores[offset : offset + size]))
        offset += size
    return groups


def evaluate(
    labels: list[int],
    scores: list[float],
    group_sizes: list[int],
    *,
    scorer_name: str,
) -> RankingMetrics:
    """Compute all ranking metrics for one scorer.

    Args:
        labels: Graded relevance, flat and ordered by group.
        scores: Predicted scores, aligned with ``labels``.
        group_sizes: Rows per query group.
        scorer_name: Used in logs and warnings.

    Returns:
        Averaged metrics, with a circularity warning attached when NDCG@10 is
        implausibly high.
    """
    groups = _iter_groups(labels, scores, group_sizes)
    if not groups:  # pragma: no cover - defensive
        msg = "cannot evaluate an empty split"
        raise ValueError(msg)

    ndcg5 = sum(ndcg_at_k(g, s, 5) for g, s in groups) / len(groups)
    ndcg10 = sum(ndcg_at_k(g, s, 10) for g, s in groups) / len(groups)
    the_map = sum(average_precision(g, s) for g, s in groups) / len(groups)
    mrr = sum(reciprocal_rank(g, s) for g, s in groups) / len(groups)

    warnings: list[str] = []
    if ndcg10 > CIRCULARITY_THRESHOLD:
        warning = (
            f"NDCG@10 of {ndcg10:.4f} exceeds {CIRCULARITY_THRESHOLD}. On synthetic data "
            f"this indicates label leakage rather than model quality: the label function "
            f"is probably recoverable from the features. Review the anti-circularity "
            f"design in data/labels.py before trusting this result."
        )
        warnings.append(warning)
        logger.warning("circularity_suspected", scorer=scorer_name, ndcg_at_10=ndcg10)

    logger.info(
        "ranking_evaluated",
        scorer=scorer_name,
        ndcg_at_5=round(ndcg5, 4),
        ndcg_at_10=round(ndcg10, 4),
        mean_average_precision=round(the_map, 4),
        mean_reciprocal_rank=round(mrr, 4),
        n_groups=len(groups),
    )

    return RankingMetrics(
        ndcg_at_5=ndcg5,
        ndcg_at_10=ndcg10,
        mean_average_precision=the_map,
        mean_reciprocal_rank=mrr,
        n_groups=len(groups),
        warnings=tuple(warnings),
    )


@dataclass(frozen=True)
class Comparison:
    """Model measured against the rule-based baseline."""

    model: RankingMetrics
    baseline: RankingMetrics

    @property
    def ndcg_at_10_delta(self) -> float:
        """How much NDCG@10 the model adds over the baseline."""
        return self.model.ndcg_at_10 - self.baseline.ndcg_at_10

    @property
    def ndcg_at_10_lift(self) -> float:
        """Relative improvement over the baseline."""
        if self.baseline.ndcg_at_10 == 0.0:  # pragma: no cover - defensive
            return 0.0
        return self.ndcg_at_10_delta / self.baseline.ndcg_at_10

    @property
    def model_beats_baseline(self) -> bool:
        """Whether the model justifies its own existence.

        One NDCG point is within noise for a few dozen validation groups.
        Anything smaller than this should be reported as "no meaningful
        improvement" rather than dressed up as a win.
        """
        return self.ndcg_at_10_delta >= 0.01

    def to_dict(self) -> dict[str, float | bool]:
        """Flat mapping for metrics.json."""
        return {
            **{f"model_{k}": v for k, v in self.model.to_dict().items()},
            **{f"baseline_{k}": v for k, v in self.baseline.to_dict().items()},
            "ndcg_at_10_delta": self.ndcg_at_10_delta,
            "ndcg_at_10_lift": self.ndcg_at_10_lift,
            "model_beats_baseline": self.model_beats_baseline,
        }
