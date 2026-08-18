"""Job posting model.

A posting is also a **query group** for the ranker. LambdaRank learns to order
candidates within a group, so one posting equals one group, and the train and
validation split is performed on whole postings rather than on individual
candidates.
"""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from guardmatch.schemas.candidate import sorted_values
from guardmatch.schemas.enums import CertificationCode, ShiftType, SiteType


class Job(BaseModel):
    """A vacancy that candidates are ranked against."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    job_id: str = Field(description="Stable identifier. Also the ranking query group key.")

    required_certifications: frozenset[CertificationCode] = Field(
        default_factory=frozenset,
        description="Certifications the role calls for. Those also listed in "
        "CRITICAL_CERTIFICATIONS gate eligibility rather than merely adding value.",
    )
    min_years_experience: float = Field(default=0.0, ge=0, le=40)
    shift_pattern: ShiftType
    site_type: SiteType
    driving_required: bool = False

    description: str = Field(default="", description="Free text. Not currently parsed.")

    @field_serializer("required_certifications")
    def _serialise_sets(self, value: Iterable[str]) -> list[str]:
        return sorted_values(value)

    @property
    def critical_certifications(self) -> frozenset[CertificationCode]:
        """Required certifications that gate eligibility."""
        from guardmatch.schemas.enums import CRITICAL_CERTIFICATIONS

        return self.required_certifications & CRITICAL_CERTIFICATIONS
