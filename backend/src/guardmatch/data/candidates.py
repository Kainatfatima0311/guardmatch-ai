"""Synthetic candidate generator.

Produces :class:`GeneratedCandidate` objects, each carrying both a free-text CV
and the ground-truth values that CV was written from. The ground truth is what
lets parser tests assert that extraction recovered what was actually put in,
rather than merely that it returned *something*.

Two properties matter more than realism of prose.

**Phrasing variety.** Each fact is written using a randomly chosen variant from
``vocab``. A generator that always wrote "SIA licence" would train the parser on
a vocabulary of one.

**Reproducibility.** Everything is driven by a single seeded ``random.Random``
instance rather than the module-level ``random`` functions, so two runs with the
same seed produce byte-identical output and no other library's use of randomness
can perturb it.

Note that a CV deliberately does *not* always state every fact. Real applications
omit things, and a parser that has never seen an omission will treat one as
malformed input rather than as missing data.
"""

from __future__ import annotations

import random

from faker import Faker

from guardmatch.data.vocab import (
    CERTIFICATION_PHRASINGS,
    DRIVING_PHRASINGS,
    EXPERIENCE_TEMPLATES,
    NO_DRIVING_PHRASINGS,
    NUMBER_WORDS,
    ROLE_TITLES,
    SECTION_HEADINGS,
    SHIFT_PHRASINGS,
    SITE_PHRASINGS,
    SUMMARY_TEMPLATES,
)
from guardmatch.schemas.candidate import GeneratedCandidate
from guardmatch.schemas.enums import CertificationCode, ShiftType, SiteType

# Probability that a stated fact is written into the CV at all. Below 1.0 so the
# parser encounters genuinely absent information, which must become None rather
# than a default.
_P_STATE_EXPERIENCE = 0.92
_P_STATE_AVAILABILITY = 0.85
_P_STATE_DRIVING = 0.70
_P_STATE_SITE_HISTORY = 0.80

# Experience is skewed towards the lower end: most guard applicants are not
# twenty-year veterans, and a uniform distribution would make the experience
# features far more discriminative than they are in reality.
_EXPERIENCE_WEIGHTS: tuple[tuple[float, float], ...] = (
    (0.0, 1.0),
    (1.0, 3.0),
    (3.0, 6.0),
    (6.0, 10.0),
    (10.0, 25.0),
)
_EXPERIENCE_BUCKET_WEIGHTS = (0.18, 0.30, 0.26, 0.16, 0.10)

# Certification prevalence. The security licence is common because it gates the
# job; specialist certifications are rare, which is what makes them informative.
_CERT_PREVALENCE: dict[CertificationCode, float] = {
    CertificationCode.SECURITY_LICENCE: 0.78,
    CertificationCode.FIRST_AID: 0.52,
    CertificationCode.CPR: 0.34,
    CertificationCode.FIRE_SAFETY: 0.41,
    CertificationCode.CCTV_OPERATION: 0.29,
    CertificationCode.CONFLICT_MANAGEMENT: 0.31,
    CertificationCode.DOG_HANDLING: 0.07,
    CertificationCode.CLOSE_PROTECTION: 0.09,
    CertificationCode.HEALTH_AND_SAFETY: 0.44,
}

_SHIFT_PREVALENCE: dict[ShiftType, float] = {
    ShiftType.DAY: 0.86,
    ShiftType.NIGHT: 0.47,
    ShiftType.WEEKEND: 0.58,
    ShiftType.ROTATING: 0.39,
}

_CURRENT_YEAR = 2026


def _draw_experience(rng: random.Random) -> float:
    """Draw years of experience from the skewed bucket distribution."""
    low, high = rng.choices(_EXPERIENCE_WEIGHTS, weights=_EXPERIENCE_BUCKET_WEIGHTS, k=1)[0]
    return round(rng.uniform(low, high), 1)


def _draw_subset[T](rng: random.Random, prevalence: dict[T, float]) -> frozenset[T]:
    """Draw a subset by independent per-item probability."""
    return frozenset(item for item, p in prevalence.items() if rng.random() < p)


def _render_experience(rng: random.Random, years: float) -> str:
    """Write a years-of-experience statement in one of several forms."""
    template = rng.choice(EXPERIENCE_TEMPLATES)
    whole = round(years)

    # The word-number form only exists for values we have words for; fall back
    # rather than emitting "seven point four years".
    if "{words}" in template and whole not in NUMBER_WORDS:
        template = "{years} years of experience"

    end = _CURRENT_YEAR
    start = end - max(whole, 1)
    display_years = whole if template.startswith(("{words}", "{start}")) else years

    return template.format(
        years=display_years if display_years != int(display_years) else int(display_years),
        words=NUMBER_WORDS.get(whole, str(whole)),
        start=start,
        end=end,
    )


def _render_certifications(rng: random.Random, certs: frozenset[CertificationCode]) -> list[str]:
    """Write each certification using a randomly chosen surface form."""
    lines: list[str] = []
    for cert in sorted(certs):
        phrasing = rng.choice(CERTIFICATION_PHRASINGS[cert])
        lines.append(f"- {phrasing}")
    return lines


def _render_availability(rng: random.Random, shifts: frozenset[ShiftType]) -> str:
    """Write shift availability as prose."""
    phrasings = [rng.choice(SHIFT_PHRASINGS[shift]) for shift in sorted(shifts)]
    if not phrasings:
        return "Availability to be discussed."
    if len(phrasings) == 1:
        return f"Available for {phrasings[0]}."
    return f"Available for {', '.join(phrasings[:-1])} and {phrasings[-1]}."


def _render_roles(
    rng: random.Random,
    faker: Faker,
    role_count: int,
    sites: frozenset[SiteType],
    months_since_last: int | None,
) -> list[str]:
    """Write a short employment history."""
    if role_count == 0:
        return ["No previous security roles."]

    site_list = sorted(sites) or [rng.choice(list(SiteType))]
    lines: list[str] = []

    # Walk backwards from the most recent role. The first entry's end date
    # encodes months_since_last_role, which the parser has to recover.
    months_ago = months_since_last if months_since_last is not None else 0
    for index in range(role_count):
        site = site_list[index % len(site_list)]
        site_phrase = rng.choice(SITE_PHRASINGS[site])
        title = rng.choice(ROLE_TITLES)
        company = faker.company()

        duration = rng.randint(8, 42)
        end_month_offset = months_ago
        start_month_offset = months_ago + duration

        end_year = _CURRENT_YEAR - end_month_offset // 12
        start_year = _CURRENT_YEAR - start_month_offset // 12

        if index == 0 and months_ago == 0:
            period = f"{start_year} - present"
        else:
            period = f"{start_year} - {end_year}"

        lines.append(f"{title}, {company} ({period}) - {site_phrase}")
        months_ago = start_month_offset + rng.randint(0, 6)

    return lines


def _build_cv_text(
    rng: random.Random,
    faker: Faker,
    *,
    years: float,
    certs: frozenset[CertificationCode],
    shifts: frozenset[ShiftType],
    sites: frozenset[SiteType],
    role_count: int,
    months_since_last: int | None,
    driving: bool,
) -> str:
    """Assemble a CV from the drawn facts.

    Section order is shuffled and some sections are omitted, so the parser
    cannot rely on position.
    """
    experience_phrase = _render_experience(rng, years)
    title = rng.choice(ROLE_TITLES)

    sections: list[tuple[str, list[str]]] = []

    summary = rng.choice(SUMMARY_TEMPLATES).format(
        title=title.lower(),
        experience=experience_phrase if rng.random() < _P_STATE_EXPERIENCE else "a solid record",
    )
    sections.append((rng.choice(SECTION_HEADINGS["summary"]), [summary]))

    if rng.random() < _P_STATE_SITE_HISTORY:
        sections.append(
            (
                rng.choice(SECTION_HEADINGS["experience"]),
                _render_roles(rng, faker, role_count, sites, months_since_last),
            )
        )

    if certs:
        sections.append(
            (rng.choice(SECTION_HEADINGS["certifications"]), _render_certifications(rng, certs))
        )

    if rng.random() < _P_STATE_AVAILABILITY:
        sections.append(
            (rng.choice(SECTION_HEADINGS["availability"]), [_render_availability(rng, shifts)])
        )

    if rng.random() < _P_STATE_DRIVING:
        phrase = rng.choice(DRIVING_PHRASINGS if driving else NO_DRIVING_PHRASINGS)
        sections.append(("ADDITIONAL", [phrase]))

    # Keep the summary first, as CVs almost always do, but vary the rest.
    head, tail = sections[0], sections[1:]
    rng.shuffle(tail)

    parts: list[str] = []
    for heading, lines in [head, *tail]:
        parts.append(heading)
        parts.extend(lines)
        parts.append("")

    return "\n".join(parts).strip()


def generate_candidates(n: int, seed: int) -> list[GeneratedCandidate]:
    """Generate ``n`` synthetic candidates reproducibly.

    Args:
        n: How many candidates to generate.
        seed: Seed for both the random number generator and Faker.

    Returns:
        Candidates carrying CV text and the ground truth it was written from.
    """
    rng = random.Random(seed)
    faker = Faker()
    Faker.seed(seed)

    candidates: list[GeneratedCandidate] = []

    for index in range(n):
        years = _draw_experience(rng)
        certs = _draw_subset(rng, _CERT_PREVALENCE)
        shifts = _draw_subset(rng, _SHIFT_PREVALENCE)

        # Role count tracks experience: someone with fifteen years has usually
        # held more than one post. Independent draws would produce twenty-year
        # veterans on their first job.
        role_count = min(6, max(0, int(years / 2.5) + rng.randint(-1, 1)))

        sites = (
            frozenset(rng.sample(list(SiteType), k=min(role_count, rng.randint(1, 3))))
            if role_count
            else frozenset()
        )

        # Most applicants are currently or recently employed; a long gap is the
        # informative minority.
        months_since_last = (
            None
            if role_count == 0
            else rng.choices([0, 3, 9, 24], weights=[0.55, 0.25, 0.13, 0.07])[0]
        )

        driving = rng.random() < 0.62

        cv_text = _build_cv_text(
            rng,
            faker,
            years=years,
            certs=certs,
            shifts=shifts,
            sites=sites,
            role_count=role_count,
            months_since_last=months_since_last,
            driving=driving,
        )

        candidates.append(
            GeneratedCandidate(
                candidate_id=f"c_{index:05d}",
                cv_text=cv_text,
                true_years_experience=years,
                true_certifications=certs,
                true_driving_licence=driving,
                true_shift_availability=shifts,
                true_site_experience=sites,
                true_previous_role_count=role_count,
                true_months_since_last_role=months_since_last,
            )
        )

    return candidates
