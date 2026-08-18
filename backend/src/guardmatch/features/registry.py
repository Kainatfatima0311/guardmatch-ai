"""The feature contract: which features exist, and in what order.

LightGBM does not see feature names at prediction time — it sees a positional
array. If a model was trained with ``exp_gap`` at index 0 and is served with
``licence_match`` there instead, every prediction is computed from the wrong
numbers. Nothing crashes, no error is logged, and the scores look entirely
reasonable. Train/serve skew of this kind is among the hardest production bugs
to notice, because the only symptom is that the model is quietly worse than it
was.

This module makes that impossible. The canonical order is defined once, written
into every model's ``feature_names.json``, and verified on load. A mismatch
fails startup rather than serving wrong answers.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from guardmatch.core.exceptions import FeatureContractError
from guardmatch.features.blocklist import assert_feature_names_clean

# The canonical feature order. Append-only in practice: reordering this list
# invalidates every previously trained model, which is why a change here
# requires a major version bump under the versioning scheme in the design doc.
FEATURE_NAMES: tuple[str, ...] = (
    "exp_gap",
    "exp_ratio",
    "licence_match",
    "cert_overlap_ratio",
    "cert_overlap_count",
    "missing_critical_cert",
    "shift_match",
    "site_type_match",
    "driving_required_match",
    "extra_cert_count",
    "role_count",
    "recency_months",
)

# Verified at import. A protected attribute cannot enter the model by being
# renamed into this list — the package fails to load instead.
assert_feature_names_clean(FEATURE_NAMES)


def to_vector(features: Mapping[str, float | None]) -> list[float | None]:
    """Order one feature mapping into the canonical positional vector.

    Raises:
        FeatureContractError: The mapping's keys do not match the contract.
    """
    missing = sorted(set(FEATURE_NAMES) - set(features))
    unexpected = sorted(set(features) - set(FEATURE_NAMES))

    if missing or unexpected:
        msg = (
            f"feature mapping does not match the contract "
            f"(missing={missing}, unexpected={unexpected})"
        )
        raise FeatureContractError(msg)

    return [features[name] for name in FEATURE_NAMES]


def to_matrix(rows: Sequence[Mapping[str, float | None]]) -> list[list[float | None]]:
    """Order many feature mappings into a positional matrix."""
    return [to_vector(row) for row in rows]


def validate_against(names: Sequence[str]) -> None:
    """Check a stored feature list against the current contract.

    Called when loading a model artifact. Both membership and order are checked,
    since a reordering is just as damaging as a missing column and far less
    obvious.

    Raises:
        FeatureContractError: The stored list disagrees with the contract.
    """
    stored = tuple(names)

    if stored == FEATURE_NAMES:
        return

    if set(stored) == set(FEATURE_NAMES):
        msg = (
            "model feature ORDER differs from the current contract. The model would be "
            f"served with mismatched columns. stored={stored} expected={FEATURE_NAMES}"
        )
    else:
        msg = (
            "model feature SET differs from the current contract. "
            f"only_in_model={sorted(set(stored) - set(FEATURE_NAMES))} "
            f"only_in_code={sorted(set(FEATURE_NAMES) - set(stored))}"
        )
    raise FeatureContractError(msg)
