"""Explainability tests.

The single most important assertion here is **additivity**: the base value plus
every contribution must reconstruct the raw score exactly. An explanation that
does not sum to the thing it explains is not an explanation, it is a plausible
story told alongside a number.

The second theme is **wording discipline**. A LambdaRank contribution is
movement on an internal scale, and any phrasing that sounds like a probability
invites the worst misreading of this system. Several tests exist purely to keep
percentage and likelihood language out of the sentences a reviewer reads.
"""

from __future__ import annotations

import re
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pytest

from guardmatch.explain.reasons import DESCRIBERS, build_reasons, describe
from guardmatch.explain.shap_explainer import (
    ADDITIVITY_TOLERANCE,
    Contribution,
    Explainer,
    ShapExplanation,
)
from guardmatch.features.registry import FEATURE_NAMES

MODELS_ROOT = Path(__file__).resolve().parents[1] / "models"


@pytest.fixture(scope="module")
def booster() -> lgb.Booster:
    """A small ranker trained in-process, so tests do not depend on an artifact."""
    rng = np.random.default_rng(3)
    rows = 120
    features = rng.random((rows, len(FEATURE_NAMES)))
    # A learnable signal, so contributions are non-trivial.
    labels = (features[:, 2] * 2 + features[:, 6] * 1.5 + rng.random(rows) * 0.3).round().astype(
        int
    )
    labels = np.clip(labels, 0, 3)

    dataset = lgb.Dataset(features, label=labels, group=[20] * 6, free_raw_data=False)
    return lgb.train(
        {
            "objective": "lambdarank",
            "metric": "ndcg",
            "num_leaves": 7,
            "learning_rate": 0.1,
            "verbosity": -1,
            "seed": 3,
        },
        dataset,
        num_boost_round=25,
    )


@pytest.fixture(scope="module")
def explainer(booster: lgb.Booster) -> Explainer:
    return Explainer(booster)


@pytest.fixture(scope="module")
def sample_matrix() -> np.ndarray:
    rng = np.random.default_rng(11)
    matrix = rng.random((15, len(FEATURE_NAMES)))
    # Include unknowns, since NaN handling is the interesting path.
    matrix[0, 0] = np.nan
    matrix[1, 6] = np.nan
    return matrix


# ---------------------------------------------------------------------------
# Additivity
# ---------------------------------------------------------------------------


def test_contributions_reconstruct_the_score(
    explainer: Explainer, booster: lgb.Booster, sample_matrix: np.ndarray
) -> None:
    """Base value plus contributions must equal the model's own output.

    This is what separates an explanation from a story told next to a number.
    """
    explanations = explainer.explain_matrix(sample_matrix)
    predicted = np.asarray(booster.predict(sample_matrix)).ravel()

    for index, explanation in enumerate(explanations):
        assert explanation.total == pytest.approx(
            float(predicted[index]), abs=ADDITIVITY_TOLERANCE
        )


def test_every_feature_is_accounted_for(
    explainer: Explainer, sample_matrix: np.ndarray
) -> None:
    """A feature silently omitted from the explanation would hide its effect."""
    explanation = explainer.explain_matrix(sample_matrix)[0]
    assert tuple(c.feature for c in explanation.contributions) == FEATURE_NAMES


def test_unknown_values_are_reported_as_none(
    explainer: Explainer, sample_matrix: np.ndarray
) -> None:
    explanation = explainer.explain_matrix(sample_matrix)[0]
    by_name = {c.feature: c for c in explanation.contributions}
    assert by_name[FEATURE_NAMES[0]].value is None


def test_contributions_rank_by_absolute_effect(
    explainer: Explainer, sample_matrix: np.ndarray
) -> None:
    ranked = explainer.explain_matrix(sample_matrix)[0].ranked()
    magnitudes = [abs(c.contribution) for c in ranked]
    assert magnitudes == sorted(magnitudes, reverse=True)


def test_global_importance_covers_every_feature(
    explainer: Explainer, sample_matrix: np.ndarray
) -> None:
    importance = explainer.global_importance(sample_matrix)
    assert set(importance) == set(FEATURE_NAMES)
    assert all(value >= 0 for value in importance.values())


# ---------------------------------------------------------------------------
# Wording
# ---------------------------------------------------------------------------


def test_every_feature_has_a_describer() -> None:
    """A feature without wording falls back to raw text a reviewer cannot use."""
    assert set(DESCRIBERS) == set(FEATURE_NAMES)


PROBABILITY_LANGUAGE = re.compile(
    r"\b(probabilit|likelihood|likely|chance|odds|confidence|percent chance)\b|%\s*(chance|likely)",
    re.IGNORECASE,
)


def test_reasons_never_use_probability_language(
    explainer: Explainer, sample_matrix: np.ndarray
) -> None:
    """A ranking score is not a probability, and the wording must not suggest one.

    This is the most likely way the system gets misread, so it is asserted
    rather than left to reviewer discipline.
    """
    for explanation in explainer.explain_matrix(sample_matrix):
        for reason in build_reasons(explanation):
            assert not PROBABILITY_LANGUAGE.search(reason), reason


def test_reasons_never_quote_the_raw_contribution(
    explainer: Explainer, sample_matrix: np.ndarray
) -> None:
    """Showing "+0.94" to a reviewer invites reading it as a percentage.

    The exact figure stays in the contributions array for anyone auditing.
    """
    for explanation in explainer.explain_matrix(sample_matrix):
        for reason in build_reasons(explanation):
            assert "+0." not in reason
            assert "-0." not in reason


def test_direction_follows_the_contribution_not_the_fact() -> None:
    """A positive-sounding fact with a negative contribution must say so.

    Hiding the mismatch would conceal exactly the behaviour a reviewer needs to
    question.
    """
    positive_fact_negative_effect = Contribution(
        feature="licence_match", value=1.0, contribution=-0.8
    )
    sentence = describe(positive_fact_negative_effect, share=0.5)

    assert "Holds the required security licence" in sentence
    assert "against" in sentence


def test_strength_scales_with_share() -> None:
    contribution = Contribution(feature="shift_match", value=1.0, contribution=0.5)
    assert "strongly" in describe(contribution, share=0.40)
    assert "moderately" in describe(contribution, share=0.15)
    assert "slightly" in describe(contribution, share=0.03)


@pytest.mark.parametrize(
    ("feature", "value", "expected"),
    [
        ("shift_match", None, "not stated"),
        ("driving_required_match", None, "not stated"),
        ("role_count", None, "No employment history"),
        ("exp_gap", None, "could not be determined"),
    ],
)
def test_unknowns_are_named_as_unknowns(feature: str, value: float | None, expected: str) -> None:
    """A reviewer must be able to tell "unavailable" from "did not say"."""
    sentence = describe(Contribution(feature=feature, value=value, contribution=0.1), share=0.3)
    assert expected in sentence


def test_reason_count_is_capped(explainer: Explainer, sample_matrix: np.ndarray) -> None:
    explanation = explainer.explain_matrix(sample_matrix)[0]
    assert len(build_reasons(explanation, top_n=3)) <= 3


def test_zero_contributions_produce_a_usable_message() -> None:
    """An empty list would read as a rendering bug rather than as information."""
    explanation = ShapExplanation(
        base_value=0.5,
        contributions=tuple(
            Contribution(feature=name, value=0.0, contribution=0.0) for name in FEATURE_NAMES
        ),
    )
    reasons = build_reasons(explanation)
    assert len(reasons) == 1
    assert "average" in reasons[0]


# ---------------------------------------------------------------------------
# Against the released artifact
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not (MODELS_ROOT / "v0.1.0").is_dir(), reason="model v0.1.0 has not been trained"
)
def test_released_model_explanations_are_additive() -> None:
    """The shipped artifact must explain itself, not just the test fixture."""
    from guardmatch.registry.artifacts import load_model

    loaded = load_model(MODELS_ROOT, "v0.1.0")
    explainer = Explainer(loaded.booster)

    rng = np.random.default_rng(5)
    matrix = rng.random((10, len(FEATURE_NAMES)))
    predicted = np.asarray(loaded.booster.predict(matrix)).ravel()

    for index, explanation in enumerate(explainer.explain_matrix(matrix)):
        assert explanation.total == pytest.approx(
            float(predicted[index]), abs=ADDITIVITY_TOLERANCE
        )
