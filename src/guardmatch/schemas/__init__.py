"""Shared data contracts.

Re-exported here so callers import from ``guardmatch.schemas`` rather than
reaching into individual modules, which keeps the internal layout free to change.
"""

from guardmatch.schemas.candidate import Candidate, GeneratedCandidate, ParsedProfile
from guardmatch.schemas.enums import (
    CRITICAL_CERTIFICATIONS,
    CertificationCode,
    RelevanceGrade,
    ShiftType,
    SiteType,
)
from guardmatch.schemas.job import Job
from guardmatch.schemas.scoring import (
    SCORE_TYPE,
    Explanation,
    FeatureContribution,
    HealthResponse,
    ModelInfoResponse,
    ParseRequest,
    ParseResponse,
    RankRequest,
    RankResponse,
    ReadyResponse,
    ScoredCandidate,
    ScoreRequest,
    ScoreResponse,
)

__all__ = [
    "CRITICAL_CERTIFICATIONS",
    "SCORE_TYPE",
    "Candidate",
    "CertificationCode",
    "Explanation",
    "FeatureContribution",
    "GeneratedCandidate",
    "HealthResponse",
    "Job",
    "ModelInfoResponse",
    "ParseRequest",
    "ParseResponse",
    "ParsedProfile",
    "RankRequest",
    "RankResponse",
    "ReadyResponse",
    "RelevanceGrade",
    "ScoreRequest",
    "ScoreResponse",
    "ScoredCandidate",
    "ShiftType",
    "SiteType",
]
