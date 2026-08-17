"""A deliberately simple rule-based scorer.

This is **not a competing model**. It is a measuring stick.

An NDCG of 0.82 is an uninterpretable number on its own. Compared against a
scorer that anyone could have written in twenty lines without any machine
learning, it becomes a statement: either the model learned something the rule
did not, or it did not.

If LambdaRank fails to beat this by a meaningful margin, the honest conclusion
is that machine learning added nothing to this problem, and that conclusion
belongs in the model card. A project that reports it is more trustworthy than
one that quietly omits the comparison — and the omission is the norm, which is
precisely why it is worth not repeating.

The weights below are hand-chosen and not tuned. Tuning them would turn the
baseline into a second model and destroy its value as a reference point.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

# Hand-set, never fitted. These express an obvious reading of the job
# requirements: hold what is asked for, clear the experience bar, be available.
_W_CERT_OVERLAP = 2.0
_W_EXPERIENCE_MET = 1.0
_W_SHIFT_MATCH = 0.5
_W_MISSING_CRITICAL = 1.5


def baseline_score(features: Mapping[str, float | None]) -> float:
    """Score one (candidate, job) pair using fixed rules.

    Unknown values are treated as neutral rather than as failures, matching how
    the model handles missing data. Scoring an unknown as zero would make the
    baseline artificially harsh and flatter the model by comparison.
    """
    score = _W_CERT_OVERLAP * (features["cert_overlap_ratio"] or 0.0)

    exp_gap = features["exp_gap"]
    if exp_gap is not None and exp_gap >= 0:
        score += _W_EXPERIENCE_MET

    score += _W_SHIFT_MATCH * (features["shift_match"] or 0.0)
    score -= _W_MISSING_CRITICAL * (features["missing_critical_cert"] or 0.0)

    return score


def baseline_scores(
    rows: Sequence[Sequence[float | None]], feature_names: Sequence[str]
) -> list[float]:
    """Score a positional feature matrix.

    Takes the same matrix the model receives, so both are evaluated on identical
    inputs through identical plumbing. A baseline fed different data would not be
    a fair reference.
    """
    index = {name: position for position, name in enumerate(feature_names)}
    return [
        baseline_score({name: row[position] for name, position in index.items()}) for row in rows
    ]
