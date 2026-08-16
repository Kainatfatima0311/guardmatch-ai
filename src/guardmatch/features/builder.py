"""Turning a (candidate, job) pair into numbers the model can use.

Features describe a **pair**, never a candidate alone. The same guard is an
excellent fit for a daytime retail post and a poor one for a night industrial
site, and a feature set that could not express that difference would reduce the
whole system to a global "candidate quality" score wearing a job-matching label.

**Unknown stays unknown.** Where the parser could not determine a fact, the
feature is ``None`` and LightGBM handles the gap natively. The alternative —
imputing a zero or a median — would convert a missing line in someone's CV into
a concrete claim about them, and the resulting penalty would be invisible in
every metric except the fairness audit. That is the same defaulting mistake the
parser had to be corrected for twice, and it is not repeated here.

**Nothing this module touches carries demographic information.** ``ParsedProfile``
has no such fields by construction, and ``assert_no_protected_fields`` re-checks
at runtime in case that ever changes.
"""

from __future__ import annotations

from guardmatch.features.blocklist import assert_no_protected_fields
from guardmatch.schemas.candidate import ParsedProfile
from guardmatch.schemas.enums import CRITICAL_CERTIFICATIONS, CertificationCode
from guardmatch.schemas.job import Job

# Caps that flatten the tail of a distribution. Both are proxy mitigations: the
# upper end of career length and role count is where the age signal is strongest,
# and an uncapped value would let the model read it.
MAX_ROLE_COUNT = 6
MAX_RECENCY_MONTHS = 240
MAX_EXPERIENCE_RATIO = 5.0


def build_features(profile: ParsedProfile, job: Job) -> dict[str, float | None]:
    """Compute the feature vector for one (candidate, job) pair.

    Args:
        profile: Structured facts extracted from the candidate's CV.
        job: The posting being ranked against.

    Returns:
        Feature name to value, with ``None`` wherever the underlying fact is
        unknown.

    Raises:
        ProtectedAttributeError: A protected attribute is present on either
            input.
    """
    assert_no_protected_fields(profile.model_dump(), context="ParsedProfile")
    assert_no_protected_fields(job.model_dump(), context="Job")

    required = job.required_certifications
    held = profile.certifications

    # -- Experience -------------------------------------------------------
    years = profile.years_experience
    exp_gap = None if years is None else years - job.min_years_experience
    exp_ratio = (
        None
        if years is None
        else min(years / max(job.min_years_experience, 1.0), MAX_EXPERIENCE_RATIO)
    )

    # -- Certifications ---------------------------------------------------
    # Always known: an empty certification set means the CV listed none, which
    # is a statement, unlike an absent field.
    overlap = required & held
    cert_overlap_count = float(len(overlap))
    cert_overlap_ratio = len(overlap) / len(required) if required else 1.0

    missing_critical = bool((required & CRITICAL_CERTIFICATIONS) - held)
    licence_match = float(
        CertificationCode.SECURITY_LICENCE in held
        if CertificationCode.SECURITY_LICENCE in required
        # Not required, so the candidate cannot fail to meet it. Holding it
        # anyway is credited through extra_cert_count rather than here.
        else 1.0
    )
    extra_cert_count = float(len(held - required))

    # -- Availability -----------------------------------------------------
    # An empty availability set means the CV never stated a working pattern, so
    # the match is unknown rather than false.
    shift_match = (
        None if not profile.shift_availability else float(job.shift_pattern in profile.shift_availability)
    )

    # -- History ----------------------------------------------------------
    # Site experience is only meaningful when an employment section was present.
    # Without one, an empty site set reflects a missing section, not a candidate
    # who has never worked this type of site.
    role_count = profile.previous_role_count
    site_type_match = (
        None if role_count is None else float(job.site_type in profile.site_experience)
    )

    # -- Driving ----------------------------------------------------------
    if not job.driving_required:
        driving_required_match = 1.0
    elif profile.driving_licence is None:
        driving_required_match = None
    else:
        driving_required_match = float(profile.driving_licence)

    recency = profile.months_since_last_role

    return {
        "exp_gap": exp_gap,
        "exp_ratio": exp_ratio,
        "licence_match": licence_match,
        "cert_overlap_ratio": cert_overlap_ratio,
        "cert_overlap_count": cert_overlap_count,
        "missing_critical_cert": float(missing_critical),
        "shift_match": shift_match,
        "site_type_match": site_type_match,
        "driving_required_match": driving_required_match,
        "extra_cert_count": extra_cert_count,
        "role_count": None if role_count is None else float(min(role_count, MAX_ROLE_COUNT)),
        "recency_months": None if recency is None else float(min(recency, MAX_RECENCY_MONTHS)),
    }
