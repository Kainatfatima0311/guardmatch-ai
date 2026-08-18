"""Turning SHAP numbers into sentences a reviewer can act on.

Two layers travel with every ranked candidate. The numeric contributions are the
auditable record — exact, reproducible, and what an investigator would want if a
candidate ever challenged a decision. The sentences here are what the person
doing the shortlisting actually reads.

Both are returned, always. Publishing only the numbers means nobody reads them;
publishing only the sentences means nobody can check them.

Three rules shape the wording.

**No probability language.** Never "94%", never "likely to be hired", never
"confidence". A LambdaRank contribution is movement on an internal scale, and
any phrasing that sounds like a probability invites the single worst misreading
of this system.

**Direction comes from the contribution, not from the fact.** A fact that sounds
positive can carry a negative contribution. Rather than hiding that, the wording
reports what the model actually did — a surprising combination is precisely what
a reviewer needs to see.

**Unknowns are named as unknowns.** "Shift availability was not stated" is
useful; silently omitting the field is not, because the reviewer cannot tell the
difference between a candidate who is unavailable and one who forgot to mention
it.
"""

from __future__ import annotations

from collections.abc import Callable

from guardmatch.explain.shap_explainer import Contribution, ShapExplanation

# How many reasons to surface. Beyond this the tail is noise, and a wall of
# marginal factors makes the significant ones harder to see.
DEFAULT_TOP_N = 5

# Contributions below this share of the total absolute effect are not worth a
# sentence.
MIN_SHARE = 0.02


def _describe_exp_gap(value: float | None) -> str:
    if value is None:
        return "Years of experience could not be determined from the CV"
    if value >= 0:
        return f"{value:.1f} years above the minimum experience requirement"
    return f"{abs(value):.1f} years below the minimum experience requirement"


def _describe_licence(value: float | None) -> str:
    if value is None:  # pragma: no cover - always known
        return "Security licence status is unknown"
    return (
        "Holds the required security licence"
        if value >= 1.0
        else "Does not hold the required security licence"
    )


def _describe_cert_ratio(value: float | None) -> str:
    if value is None:  # pragma: no cover - always known
        return "Certification coverage is unknown"
    return f"Holds {value * 100:.0f}% of the certifications this role requires"


def _describe_cert_count(value: float | None) -> str:
    if value is None:  # pragma: no cover - always known
        return "Certification count is unknown"
    return f"Holds {value:.0f} of the required certifications"


def _describe_missing_critical(value: float | None) -> str:
    if value is None:  # pragma: no cover - always known
        return "Mandatory certification status is unknown"
    return (
        "Missing a certification this role treats as mandatory"
        if value >= 1.0
        else "Holds every mandatory certification"
    )


def _describe_shift(value: float | None) -> str:
    if value is None:
        return "Shift availability was not stated in the CV"
    return (
        "Available for the shift pattern this role needs"
        if value >= 1.0
        else "Not available for the shift pattern this role needs"
    )


def _describe_site(value: float | None) -> str:
    if value is None:
        return "No employment history was found in the CV"
    return (
        "Has prior experience at this type of site"
        if value >= 1.0
        else "No prior experience at this type of site"
    )


def _describe_driving(value: float | None) -> str:
    if value is None:
        return "Driving licence status was not stated in the CV"
    return (
        "Meets the driving requirement for this role"
        if value >= 1.0
        else "Does not hold a driving licence, which this role requires"
    )


def _describe_extra_certs(value: float | None) -> str:
    if value is None or value <= 0:  # pragma: no cover - always known
        return "No relevant certifications beyond those required"
    return f"Holds {value:.0f} relevant certifications beyond those required"


def _describe_role_count(value: float | None) -> str:
    if value is None:
        return "No employment history was found in the CV"
    if value == 0:
        return "No previous security roles"
    return f"{value:.0f} previous security roles"


def _describe_recency(value: float | None) -> str:
    if value is None:
        return "Date of the most recent role could not be determined"
    if value <= 0:
        return "Currently or very recently employed"
    return f"Most recent role ended around {value:.0f} months ago"


def _describe_exp_ratio(value: float | None) -> str:
    if value is None:
        return "Years of experience could not be determined from the CV"
    return f"Experience is {value:.1f} times the stated minimum"


DESCRIBERS: dict[str, Callable[[float | None], str]] = {
    "exp_gap": _describe_exp_gap,
    "exp_ratio": _describe_exp_ratio,
    "licence_match": _describe_licence,
    "cert_overlap_ratio": _describe_cert_ratio,
    "cert_overlap_count": _describe_cert_count,
    "missing_critical_cert": _describe_missing_critical,
    "shift_match": _describe_shift,
    "site_type_match": _describe_site,
    "driving_required_match": _describe_driving,
    "extra_cert_count": _describe_extra_certs,
    "role_count": _describe_role_count,
    "recency_months": _describe_recency,
}


def _strength(share: float) -> str:
    """Describe how much of the total effect one contribution accounts for."""
    if share >= 0.25:
        return "strong"
    if share >= 0.10:
        return "moderate"
    return "slight"


def _effect_phrase(contribution: float, share: float) -> str:
    """Say which way a factor moved the ranking, and how much.

    Deliberately vague about magnitude. Reporting "+0.94" to a reviewer invites
    the reading that it is a percentage, and the exact figure is already in the
    contributions array for anyone who needs it.
    """
    direction = "in favour" if contribution >= 0 else "against"
    return f"counted {_strength(share)}ly {direction}"


def describe(contribution: Contribution, share: float) -> str:
    """Render one contribution as a sentence."""
    describer = DESCRIBERS.get(contribution.feature)
    fact = (
        describer(contribution.value)
        if describer
        else f"{contribution.feature} = {contribution.value}"
    )
    return f"{fact} — {_effect_phrase(contribution.contribution, share)}"


def build_reasons(explanation: ShapExplanation, *, top_n: int = DEFAULT_TOP_N) -> tuple[str, ...]:
    """Render the leading contributions as plain-language sentences.

    Args:
        explanation: SHAP output for one candidate.
        top_n: How many reasons to surface.

    Returns:
        Sentences ordered by absolute effect, largest first.
    """
    ranked = explanation.ranked()
    total = sum(abs(c.contribution) for c in ranked)

    if total == 0.0:
        # Every feature contributed nothing — the candidate sits exactly at the
        # model's base value. Saying so is more useful than an empty list.
        return ("No individual factor moved this candidate away from the average.",)

    reasons: list[str] = []
    for contribution in ranked[:top_n]:
        share = abs(contribution.contribution) / total
        if share < MIN_SHARE:
            continue
        reasons.append(describe(contribution, share))

    return tuple(reasons)
