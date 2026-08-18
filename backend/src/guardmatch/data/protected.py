"""Protected attributes, held apart from everything the model can reach.

Fairness cannot be measured without demographics, and demographics must never
influence a score. Those two requirements are met by separation rather than by
discipline: these values live in their own file, keyed by candidate id, and
``guardmatch.features`` does not import this module. A static test asserts that
absence, so adding the import would fail the build rather than pass review.

The design point is that using a protected attribute should require someone to
*add* something that is not there, not merely to *forget* something that is.

**Deliberate bias injection.** With ``inject_bias`` enabled, gender is drawn
conditional on the candidate's night-shift availability. Nothing about the label
function changes. What changes is that a legitimate, job-relevant, entirely
neutral-looking feature — ``shift_match`` — becomes a proxy for a protected
attribute, and any model trained on this data will disadvantage one group
through it.

That is how discrimination usually enters a hiring model in practice: not by
someone adding a gender feature, but by a defensible feature quietly carrying
demographic information. A fairness suite that has only ever run on clean data
has never been shown to detect anything, so this switch exists to prove the
audit works. It is off by default and whatever setting was used is recorded in
the data card.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import StrEnum

from guardmatch.schemas.candidate import GeneratedCandidate
from guardmatch.schemas.enums import ShiftType


class Gender(StrEnum):
    """Recorded for fairness measurement only."""

    FEMALE = "female"
    MALE = "male"


class AgeBand(StrEnum):
    """Age as a band rather than a number, since bands are what get reported."""

    UNDER_25 = "under_25"
    AGE_25_34 = "25_34"
    AGE_35_44 = "35_44"
    AGE_45_54 = "45_54"
    AGE_55_PLUS = "55_plus"


class Nationality(StrEnum):
    """Coarse nationality grouping for fairness measurement."""

    GROUP_A = "group_a"
    GROUP_B = "group_b"
    GROUP_C = "group_c"


@dataclass(frozen=True)
class ProtectedAttributes:
    """Demographics for one candidate. Evaluation only, never a feature."""

    candidate_id: str
    gender: Gender
    age_band: AgeBand
    nationality: Nationality


# Baseline gender split when bias injection is off.
_BASE_FEMALE_RATE = 0.42

# With bias on, night availability and gender are correlated. These deviations
# from the base rate are scaled by `bias_strength`.
#
# At strength 1.0 the rates are 0.22 and 0.61 — a 0.40 gap, which is what a
# realistic caring-responsibilities correlation looks like. That turned out to
# produce an adverse impact ratio of 0.875: real directional harm that sits
# *above* the four-fifths threshold and therefore passes the audit.
#
# That is a finding about the threshold rather than about this generator. Proxy
# bias reaches the model through only one feature, and only on the subset of
# postings where that feature applies, so it is diluted twice before it shows up
# in a selection rate. Higher strengths exist so the gate demonstration has
# something it can actually detect, and both figures are reported in the
# fairness write-up.
_FEMALE_RATE_NIGHT_DELTA = -0.20
_FEMALE_RATE_NO_NIGHT_DELTA = 0.19

# Keeps scaled rates away from 0 and 1, where a group would vanish entirely and
# the audit would have nothing to compare.
_RATE_FLOOR = 0.02
_RATE_CEILING = 0.98

_AGE_BAND_WEIGHTS: dict[AgeBand, float] = {
    AgeBand.UNDER_25: 0.16,
    AgeBand.AGE_25_34: 0.29,
    AgeBand.AGE_35_44: 0.26,
    AgeBand.AGE_45_54: 0.19,
    AgeBand.AGE_55_PLUS: 0.10,
}

_NATIONALITY_WEIGHTS: dict[Nationality, float] = {
    Nationality.GROUP_A: 0.55,
    Nationality.GROUP_B: 0.30,
    Nationality.GROUP_C: 0.15,
}


def _draw_gender(
    rng: random.Random,
    *,
    available_nights: bool,
    inject_bias: bool,
    bias_strength: float = 1.0,
) -> Gender:
    """Draw gender, optionally correlated with night availability."""
    if not inject_bias:
        rate = _BASE_FEMALE_RATE
    else:
        delta = _FEMALE_RATE_NIGHT_DELTA if available_nights else _FEMALE_RATE_NO_NIGHT_DELTA
        rate = min(max(_BASE_FEMALE_RATE + delta * bias_strength, _RATE_FLOOR), _RATE_CEILING)
    return Gender.FEMALE if rng.random() < rate else Gender.MALE


def _draw_weighted[T](rng: random.Random, weights: dict[T, float]) -> T:
    """Draw one item from a weighted mapping."""
    items = list(weights.keys())
    return rng.choices(items, weights=[weights[item] for item in items], k=1)[0]


def generate_protected_attributes(
    candidates: list[GeneratedCandidate],
    seed: int,
    *,
    inject_bias: bool = False,
    bias_strength: float = 1.0,
) -> dict[str, ProtectedAttributes]:
    """Draw demographics for each candidate.

    Args:
        candidates: The candidate pool. Only ``candidate_id`` and night-shift
            availability are read.
        seed: Seed for reproducibility.
        inject_bias: When true, correlate gender with night availability so the
            fairness audit has a known bias to detect.
        bias_strength: Scales the correlation. 1.0 is a realistic
            caring-responsibilities gap of roughly 0.40, which passes the
            four-fifths threshold; higher values produce a breach the gate can
            detect.

    Returns:
        Demographics keyed by candidate id.
    """
    rng = random.Random(seed + 40_000)

    return {
        candidate.candidate_id: ProtectedAttributes(
            candidate_id=candidate.candidate_id,
            gender=_draw_gender(
                rng,
                available_nights=ShiftType.NIGHT in candidate.true_shift_availability,
                inject_bias=inject_bias,
                bias_strength=bias_strength,
            ),
            age_band=_draw_weighted(rng, _AGE_BAND_WEIGHTS),
            nationality=_draw_weighted(rng, _NATIONALITY_WEIGHTS),
        )
        for candidate in candidates
    }


def night_availability_by_gender(
    candidates: list[GeneratedCandidate],
    protected: dict[str, ProtectedAttributes],
) -> dict[Gender, float]:
    """Night-shift availability rate per gender.

    Reported in the data card. When bias injection is on, the gap between these
    rates is the mechanism by which an apparently neutral feature becomes a
    proxy — so it is the number that shows the injection actually took effect.
    """
    totals: dict[Gender, int] = dict.fromkeys(Gender, 0)
    nights: dict[Gender, int] = dict.fromkeys(Gender, 0)

    for candidate in candidates:
        attrs = protected.get(candidate.candidate_id)
        if attrs is None:
            continue
        totals[attrs.gender] += 1
        if ShiftType.NIGHT in candidate.true_shift_availability:
            nights[attrs.gender] += 1

    return {
        gender: (nights[gender] / totals[gender] if totals[gender] else 0.0) for gender in Gender
    }
