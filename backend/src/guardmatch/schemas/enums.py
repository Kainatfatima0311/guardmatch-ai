"""Closed vocabularies.

Everything the parser can recognise is enumerated here. That is the point of
using enums rather than free strings: the guard certification vocabulary is
small and closed, so an unrecognised value is a bug to surface rather than data
to pass along.

``CertificationCode`` values are the canonical form that
``parsing.normalizers`` maps every surface variant onto — "SIA", "S.I.A.",
"security licence" and "SIA badge" all resolve to
``CertificationCode.SECURITY_LICENCE``.
"""

from __future__ import annotations

from enum import StrEnum


class CertificationCode(StrEnum):
    """Certifications relevant to security guard roles."""

    SECURITY_LICENCE = "security_licence"
    FIRST_AID = "first_aid"
    CPR = "cpr"
    FIRE_SAFETY = "fire_safety"
    CCTV_OPERATION = "cctv_operation"
    CONFLICT_MANAGEMENT = "conflict_management"
    DOG_HANDLING = "dog_handling"
    CLOSE_PROTECTION = "close_protection"
    HEALTH_AND_SAFETY = "health_and_safety"


class ShiftType(StrEnum):
    """Shift patterns a candidate can cover or a site can require."""

    DAY = "day"
    NIGHT = "night"
    WEEKEND = "weekend"
    ROTATING = "rotating"


class SiteType(StrEnum):
    """Categories of site a guard may be posted to."""

    RETAIL = "retail"
    CORPORATE = "corporate"
    CONSTRUCTION = "construction"
    EVENT = "event"
    RESIDENTIAL = "residential"
    INDUSTRIAL = "industrial"


class RelevanceGrade(int):
    """Graded relevance label used by LambdaRank.

    An int subclass rather than an IntEnum so it can be handed straight to
    LightGBM, which expects plain integers in the label array.

    * 3 — strong fit, would be interviewed first
    * 2 — good fit, would be interviewed
    * 1 — marginal, only if the shortlist is thin
    * 0 — not suitable
    """

    NOT_SUITABLE = 0
    MARGINAL = 1
    GOOD = 2
    STRONG = 3


# Certifications that gate eligibility rather than merely improving a candidate.
# Absence of one of these is materially different from lacking a nice-to-have,
# and the feature builder treats it that way via `missing_critical_cert`.
CRITICAL_CERTIFICATIONS: frozenset[CertificationCode] = frozenset(
    {CertificationCode.SECURITY_LICENCE}
)
