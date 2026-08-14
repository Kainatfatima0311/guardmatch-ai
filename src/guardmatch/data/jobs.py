"""Synthetic job posting generator.

Each posting is one **query group** for LambdaRank, so the shape of this
distribution directly determines what the ranker can learn.

The requirement profiles below vary deliberately in difficulty. If every posting
asked for the same two certifications and three years of experience, every
candidate list would sort the same way and the ranker would learn a single
global ordering rather than a genuine candidate-to-job match. Hard-to-fill
postings — close protection, dog handling, night-only industrial sites — are the
ones where matching actually matters, so they have to exist in the data.

Requirements are also correlated with site type rather than drawn
independently. A construction site realistically wants health and safety and a
driver; an event wants conflict management. Independent draws would produce
postings no real employer would write, and a model trained on those learns
associations that do not exist.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from guardmatch.data.vocab import ROLE_TITLES, SITE_PHRASINGS
from guardmatch.schemas.enums import CertificationCode, ShiftType, SiteType
from guardmatch.schemas.job import Job


@dataclass(frozen=True)
class _SiteProfile:
    """What a given site type typically asks for."""

    likely_certs: tuple[CertificationCode, ...]
    shift_weights: dict[ShiftType, float]
    experience_range: tuple[float, float]
    driving_probability: float


_SITE_PROFILES: dict[SiteType, _SiteProfile] = {
    SiteType.RETAIL: _SiteProfile(
        likely_certs=(
            CertificationCode.SECURITY_LICENCE,
            CertificationCode.CONFLICT_MANAGEMENT,
            CertificationCode.CCTV_OPERATION,
        ),
        shift_weights={
            ShiftType.DAY: 0.5,
            ShiftType.WEEKEND: 0.3,
            ShiftType.ROTATING: 0.15,
            ShiftType.NIGHT: 0.05,
        },
        experience_range=(0.0, 4.0),
        driving_probability=0.15,
    ),
    SiteType.CORPORATE: _SiteProfile(
        likely_certs=(
            CertificationCode.SECURITY_LICENCE,
            CertificationCode.FIRST_AID,
            CertificationCode.CCTV_OPERATION,
        ),
        shift_weights={
            ShiftType.DAY: 0.55,
            ShiftType.ROTATING: 0.25,
            ShiftType.NIGHT: 0.15,
            ShiftType.WEEKEND: 0.05,
        },
        experience_range=(1.0, 6.0),
        driving_probability=0.20,
    ),
    SiteType.CONSTRUCTION: _SiteProfile(
        likely_certs=(
            CertificationCode.SECURITY_LICENCE,
            CertificationCode.HEALTH_AND_SAFETY,
            CertificationCode.FIRE_SAFETY,
        ),
        shift_weights={
            ShiftType.NIGHT: 0.45,
            ShiftType.ROTATING: 0.3,
            ShiftType.DAY: 0.15,
            ShiftType.WEEKEND: 0.1,
        },
        experience_range=(1.0, 5.0),
        driving_probability=0.65,
    ),
    SiteType.EVENT: _SiteProfile(
        likely_certs=(
            CertificationCode.SECURITY_LICENCE,
            CertificationCode.CONFLICT_MANAGEMENT,
            CertificationCode.FIRST_AID,
            CertificationCode.CPR,
        ),
        shift_weights={
            ShiftType.WEEKEND: 0.5,
            ShiftType.ROTATING: 0.25,
            ShiftType.NIGHT: 0.15,
            ShiftType.DAY: 0.1,
        },
        experience_range=(0.0, 3.0),
        driving_probability=0.10,
    ),
    SiteType.RESIDENTIAL: _SiteProfile(
        likely_certs=(
            CertificationCode.SECURITY_LICENCE,
            CertificationCode.CCTV_OPERATION,
            CertificationCode.FIRST_AID,
        ),
        shift_weights={
            ShiftType.NIGHT: 0.4,
            ShiftType.ROTATING: 0.35,
            ShiftType.DAY: 0.2,
            ShiftType.WEEKEND: 0.05,
        },
        experience_range=(0.0, 4.0),
        driving_probability=0.25,
    ),
    SiteType.INDUSTRIAL: _SiteProfile(
        likely_certs=(
            CertificationCode.SECURITY_LICENCE,
            CertificationCode.HEALTH_AND_SAFETY,
            CertificationCode.FIRE_SAFETY,
            CertificationCode.DOG_HANDLING,
        ),
        shift_weights={
            ShiftType.NIGHT: 0.45,
            ShiftType.ROTATING: 0.35,
            ShiftType.DAY: 0.15,
            ShiftType.WEEKEND: 0.05,
        },
        experience_range=(2.0, 8.0),
        driving_probability=0.55,
    ),
}

# A minority of postings are genuinely demanding. These are where ranking earns
# its keep, because almost every candidate is a partial match.
_P_SPECIALIST_POSTING = 0.12

_SPECIALIST_CERTS: tuple[CertificationCode, ...] = (
    CertificationCode.CLOSE_PROTECTION,
    CertificationCode.DOG_HANDLING,
)


def _draw_shift(rng: random.Random, weights: dict[ShiftType, float]) -> ShiftType:
    """Draw a shift pattern from a site's weighted distribution."""
    shifts = list(weights.keys())
    return rng.choices(shifts, weights=[weights[s] for s in shifts], k=1)[0]


def _build_description(
    rng: random.Random,
    site_type: SiteType,
    shift: ShiftType,
    min_years: float,
    certs: frozenset[CertificationCode],
) -> str:
    """Write a short posting description.

    Not currently parsed — the structured fields are authoritative. Present so
    the dataset resembles a real posting and so description parsing can be added
    later without regenerating.
    """
    title = rng.choice(ROLE_TITLES)
    site_phrase = rng.choice(SITE_PHRASINGS[site_type])
    cert_list = ", ".join(sorted(c.value.replace("_", " ") for c in certs))
    return (
        f"{title} required for a {site_phrase} site. "
        f"{shift.value.capitalize()} shift pattern. "
        f"Minimum {min_years:.0f} years of experience. "
        f"Required: {cert_list}."
    )


def generate_jobs(n: int, seed: int) -> list[Job]:
    """Generate ``n`` synthetic job postings reproducibly.

    Args:
        n: How many postings to generate.
        seed: Seed for the random number generator.

    Returns:
        Postings spanning a range of difficulty, with requirements correlated to
        site type.
    """
    # Offset from the candidate seed so postings and candidates do not share a
    # random stream. Without the offset, changing the candidate count would
    # silently change every posting too.
    rng = random.Random(seed + 10_000)

    jobs: list[Job] = []

    for index in range(n):
        site_type = rng.choice(list(SiteType))
        profile = _SITE_PROFILES[site_type]

        # Always require the licence — it gates the role — then draw one or two
        # further requirements from what this site type plausibly wants.
        required = {CertificationCode.SECURITY_LICENCE}
        optional_pool = [
            c for c in profile.likely_certs if c != CertificationCode.SECURITY_LICENCE
        ]
        required.update(rng.sample(optional_pool, k=min(len(optional_pool), rng.randint(1, 2))))

        if rng.random() < _P_SPECIALIST_POSTING:
            required.add(rng.choice(_SPECIALIST_CERTS))

        low, high = profile.experience_range
        min_years = float(round(rng.uniform(low, high)))

        shift = _draw_shift(rng, profile.shift_weights)
        driving_required = rng.random() < profile.driving_probability
        frozen_required = frozenset(required)

        jobs.append(
            Job(
                job_id=f"j_{index:04d}",
                required_certifications=frozen_required,
                min_years_experience=min_years,
                shift_pattern=shift,
                site_type=site_type,
                driving_required=driving_required,
                description=_build_description(rng, site_type, shift, min_years, frozen_required),
            )
        )

    return jobs
