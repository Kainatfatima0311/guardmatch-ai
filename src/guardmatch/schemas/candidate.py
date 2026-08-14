"""Candidate models.

There are two, and the distinction matters.

``Candidate`` is what arrives — an application, carrying free-text CV content.
``ParsedProfile`` is what the pipeline works with — structured, typed, and
containing only job-relevant facts.

Nothing downstream of the parser sees a ``Candidate``. Everything downstream
sees a ``ParsedProfile``, which has no name, no contact details and no
demographic fields at all. Protected attributes are not "excluded later"; they
are absent from the type the rest of the system is built on.

Optional fields are genuinely optional. When the parser cannot determine years
of experience, the value is ``None`` — never ``0``. Defaulting to zero would
penalise a candidate for a parsing failure, which is a fairness problem wearing
the costume of a data-cleaning convenience. LightGBM handles missing values
natively, so passing ``None`` through is both simpler and more honest.
"""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from guardmatch.schemas.enums import CertificationCode, ShiftType, SiteType


def sorted_values(value: Iterable[str]) -> list[str]:
    """Serialise a set field as a sorted list.

    Frozenset iteration order follows string hashes, and Python randomises those
    per process. Without sorting, serialising the same data twice produces two
    different files — which quietly breaks the reproducibility guarantee the
    data card makes, since a metric could no longer be traced to a dataset by
    checksum.
    """
    return sorted(str(item) for item in value)


class Candidate(BaseModel):
    """An incoming application.

    Carries free text. Held only at the boundary — the parser converts it to a
    :class:`ParsedProfile` and the rest of the pipeline uses that.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: str = Field(description="Stable identifier used to join results and logs.")
    cv_text: str = Field(min_length=1, description="Raw CV text. Never logged.")


class ParsedProfile(BaseModel):
    """Structured facts extracted from a CV.

    This is the only candidate representation the scoring pipeline sees.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: str

    years_experience: float | None = Field(
        default=None,
        ge=0,
        le=60,
        description="None when it could not be determined. Never defaulted to zero.",
    )
    certifications: frozenset[CertificationCode] = Field(default_factory=frozenset)
    driving_licence: bool = False
    shift_availability: frozenset[ShiftType] = Field(default_factory=frozenset)
    site_experience: frozenset[SiteType] = Field(default_factory=frozenset)
    previous_role_count: int = Field(default=0, ge=0)
    months_since_last_role: int | None = Field(
        default=None,
        ge=0,
        description="None when no dated prior role was found.",
    )

    parse_warnings: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Ambiguities the parser could not resolve. Surfaced in API responses so "
        "a reviewer can see where the system was unsure.",
    )

    @field_serializer("certifications", "shift_availability", "site_experience")
    def _serialise_sets(self, value: Iterable[str]) -> list[str]:
        return sorted_values(value)

    @property
    def has_security_licence(self) -> bool:
        """Whether the candidate holds the gating security licence."""
        return CertificationCode.SECURITY_LICENCE in self.certifications


class GeneratedCandidate(Candidate):
    """A synthetic candidate, carrying the ground truth used to build it.

    Used only by the data generator and its tests. The extra fields are the
    values the CV text was written from, which lets parser tests assert that
    extraction recovered what was actually put in.

    These fields never reach the feature builder — it accepts a
    :class:`ParsedProfile`, which does not have them.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    true_years_experience: float
    true_certifications: frozenset[CertificationCode]
    true_driving_licence: bool
    true_shift_availability: frozenset[ShiftType]
    true_site_experience: frozenset[SiteType]
    true_previous_role_count: int
    true_months_since_last_role: int | None

    @field_serializer(
        "true_certifications", "true_shift_availability", "true_site_experience"
    )
    def _serialise_true_sets(self, value: Iterable[str]) -> list[str]:
        return sorted_values(value)
