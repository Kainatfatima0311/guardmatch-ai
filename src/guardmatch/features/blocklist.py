"""Protected attributes, and the features that can leak them.

This module is the first of the three fairness layers described in the design
doc. It handles **prevention**: making it impossible for a protected attribute to
become a feature.

Prevention alone is not enough, which is why the second half of this file exists.
Blocking `gender` stops the obvious mistake, but a permitted, job-relevant
feature can still carry demographic information. In this project's own biased
dataset, `shift_match` does exactly that. So every allowed feature that could act
as a proxy is registered here with its mitigation, and the fairness audit
measures outcomes regardless of what the blocklist caught.

The layers are deliberately redundant. Prevention cannot see proxies;
measurement only detects harm after it has been learned. Neither is sufficient
alone.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from guardmatch.core.exceptions import ProtectedAttributeError

# Attributes that must never influence a score, in any form or transformation.
#
# Spelling variants are included because the check is a safety net for code
# written later by someone who has not read this file. A net with holes at
# `dob` and `sex` is not a net.
BLOCKED_ATTRIBUTES: frozenset[str] = frozenset(
    {
        # Sex and gender
        "gender",
        "sex",
        # Age
        "age",
        "age_band",
        "date_of_birth",
        "dob",
        "birth_date",
        "birthdate",
        "graduation_year",
        "year_of_birth",
        # Identity
        "name",
        "full_name",
        "first_name",
        "last_name",
        "surname",
        "forename",
        # Origin
        "nationality",
        "ethnicity",
        "race",
        "country_of_birth",
        "national_origin",
        # Personal circumstances
        "marital_status",
        "marital",
        "children",
        "dependants",
        "religion",
        "faith",
        "disability",
        "sexual_orientation",
        # Contact details that encode location or identity
        "postcode",
        "postal_code",
        "zip_code",
        "address",
        "email",
        "phone",
        # Imagery
        "photo",
        "photograph",
        "image",
    }
)

# Substrings that make a feature name suspect even when it is not an exact
# match. Catches things like `candidate_gender_encoded` or `age_bucket`.
_BLOCKED_SUBSTRINGS: frozenset[str] = frozenset(
    {"gender", "ethnic", "nationalit", "religio", "marital", "postcode", "disabilit"}
)

# `age` and `race` are checked separately: as bare substrings they would fire on
# innocent names like `average_score` or `trace_id`. Matched on word boundaries
# within the underscore-separated parts of a feature name instead.
_BLOCKED_TOKENS: frozenset[str] = frozenset({"age", "race", "sex", "dob", "name", "photo"})


@dataclass(frozen=True)
class ProxyRisk:
    """An allowed feature that can carry protected information indirectly."""

    feature: str
    leaks: str
    mitigation: str


# Features that are permitted but watched. Every entry here is a feature the
# model is allowed to use and the fairness audit is required to monitor.
PROXY_REGISTER: tuple[ProxyRisk, ...] = (
    ProxyRisk(
        feature="recency_months",
        leaks="Career breaks, which correlate with parental leave and therefore with gender.",
        mitigation="Capped at 240 months. Monitored in the fairness audit; a widening "
        "group gap here is a signal to bucket or drop it.",
    ),
    ProxyRisk(
        feature="role_count",
        leaks="Correlates with age — more prior roles implies a longer career.",
        mitigation="Capped at 6, which flattens the top of the distribution where the "
        "age signal is strongest.",
    ),
    ProxyRisk(
        feature="exp_gap",
        leaks="Correlates with age for the same reason as role_count.",
        mitigation="Retained. Experience relative to a stated job requirement is directly "
        "job-relevant and legally defensible, so the correct response is monitoring "
        "rather than removal.",
    ),
    ProxyRisk(
        feature="shift_match",
        leaks="Availability correlates with caring responsibilities, which correlate "
        "with gender.",
        mitigation="Monitored closely. This is the attribute the project's own bias "
        "injection exploits, so it is the known worst case rather than a hypothetical one.",
    ),
)


def _is_blocked(key: str) -> bool:
    """Whether a field or feature name refers to a protected attribute."""
    lowered = key.lower().strip()

    if lowered in BLOCKED_ATTRIBUTES:
        return True

    if any(fragment in lowered for fragment in _BLOCKED_SUBSTRINGS):
        return True

    # Token-level check for short words that would over-match as substrings.
    parts = set(lowered.replace("-", "_").split("_"))
    return bool(parts & _BLOCKED_TOKENS)


def assert_no_protected_fields(payload: Mapping[str, Any], *, context: str) -> None:
    """Raise if ``payload`` contains any protected attribute.

    Called on every input reaching the feature builder. This is a runtime net
    beneath the structural guarantee that ``ParsedProfile`` has no demographic
    fields: if someone later adds one, this fires immediately rather than at
    whatever point the resulting unfairness becomes visible.

    Args:
        payload: Field names and values about to be used.
        context: Where the payload came from, for the error message.

    Raises:
        ProtectedAttributeError: A blocked field is present.
    """
    offending = sorted(key for key in payload if _is_blocked(key))
    if offending:
        msg = (
            f"protected attribute(s) {offending} reached the feature layer via {context}. "
            f"These must never influence a score."
        )
        raise ProtectedAttributeError(msg)


def assert_feature_names_clean(names: Iterable[str]) -> None:
    """Raise if any feature name refers to a protected attribute.

    Guards the feature contract itself, so a blocked attribute cannot enter by
    being renamed into the canonical feature list.

    Raises:
        ProtectedAttributeError: A blocked name is present.
    """
    offending = sorted(name for name in names if _is_blocked(name))
    if offending:
        msg = f"feature name(s) {offending} refer to protected attributes"
        raise ProtectedAttributeError(msg)


def proxy_features() -> frozenset[str]:
    """Names of features under proxy monitoring."""
    return frozenset(risk.feature for risk in PROXY_REGISTER)
