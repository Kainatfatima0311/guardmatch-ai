"""Application configuration.

One typed, validated source of settings for the whole service. Values come from
environment variables, then from a ``.env`` file, then from the defaults here.
See ``.env.example`` for the documented set.

Two things this module deliberately does:

Settings are **validated at construction**, so an out-of-range threshold fails
at startup with a clear message rather than producing a quietly wrong fairness
report weeks later.

``fairness_top_k`` lives here rather than being passed around, because the
shortlist depth must be identical in the audit, the tests, the model card and
the reported metrics. A number duplicated across four places is a number that
will eventually disagree with itself.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from guardmatch.core.exceptions import ConfigurationError


class Settings(BaseSettings):
    """Validated application settings."""

    # ``protected_namespaces`` is cleared because several settings legitimately
    # start with "model_" (model_version, model_dir). Pydantic reserves that
    # prefix by default and would emit warnings for each one.
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        protected_namespaces=(),
        frozen=True,
    )

    # -- Model ------------------------------------------------------------
    model_version: str = Field(
        default="v0.1.0",
        description="Which versioned artifact directory to serve. Rollback is a change "
        "to this value, not a rebuild.",
    )
    model_dir: Path = Field(
        default=Path("models"),
        description="Root directory holding versioned model artifacts.",
    )

    # -- Fairness ---------------------------------------------------------
    fairness_top_k: int = Field(
        default=10,
        ge=1,
        le=1000,
        description="Shortlist depth. Every top-k fairness metric uses this value, so it "
        "must match the number of candidates a reviewer actually reviews.",
    )
    adverse_impact_threshold: float = Field(
        default=0.80,
        gt=0.0,
        le=1.0,
        description="Four-fifths rule. A group's selection rate must be at least this "
        "fraction of the highest group's rate.",
    )
    max_fairness_gap: float = Field(
        default=0.10,
        gt=0.0,
        le=1.0,
        description="Maximum permitted demographic parity and equal opportunity gap.",
    )
    min_group_size: int = Field(
        default=30,
        ge=1,
        description="Groups smaller than this are suppressed from the report rather than "
        "published as unstable noise.",
    )

    # -- API --------------------------------------------------------------
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000, ge=1, le=65535)
    max_rank_batch: int = Field(
        default=500,
        ge=1,
        le=10_000,
        description="Maximum candidates accepted in one /rank request. Unbounded batch "
        "sizes are an availability risk.",
    )

    # -- Data generation --------------------------------------------------
    random_seed: int = Field(default=42, description="Seed for reproducible generation.")
    n_candidates: int = Field(default=5_000, ge=1)
    n_jobs: int = Field(default=200, ge=1)
    inject_bias: bool = Field(
        default=False,
        description="Injects a correlation between a protected attribute and an apparently "
        "neutral feature, so the fairness audit can be shown to detect it.",
    )

    # -- Logging ----------------------------------------------------------
    log_level: str = Field(default="INFO")
    log_format: Literal["json", "console"] = Field(
        default="json",
        description="json for production and containers; console for readable local output.",
    )

    # -- Derived ----------------------------------------------------------

    @property
    def model_path(self) -> Path:
        """Directory holding the artifacts for the active model version."""
        return self.model_dir / self.model_version

    # -- Validation -------------------------------------------------------

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = value.upper()
        if upper not in allowed:
            msg = f"log_level must be one of {sorted(allowed)}, got {value!r}"
            raise ValueError(msg)
        return upper

    @field_validator("model_version")
    @classmethod
    def _validate_model_version(cls, value: str) -> str:
        # Enforced because the artifact directory name is derived from this, and
        # a stray path separator here would resolve outside models/.
        if not value.startswith("v") or "/" in value or "\\" in value:
            msg = f"model_version must look like 'v0.1.0' and contain no path separators, got {value!r}"
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def _validate_consistency(self) -> Settings:
        if self.n_candidates < self.fairness_top_k:
            msg = (
                f"n_candidates ({self.n_candidates}) is below fairness_top_k "
                f"({self.fairness_top_k}); top-k metrics would be meaningless"
            )
            raise ValueError(msg)
        return self


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings, constructed once.

    Cached so that configuration is read and validated a single time rather than
    on every request. Tests that need different settings should call
    ``get_settings.cache_clear()`` first.
    """
    try:
        return Settings()
    except Exception as exc:  # pragma: no cover - exercised via tests with bad env
        msg = f"Invalid configuration: {exc}"
        raise ConfigurationError(msg) from exc
