"""Leakage gate — protected attributes must never reach the model.

**This file is a build gate.** A failure here is not a style problem; it means
the system was about to score candidates using an attribute it is forbidden to
consider. CI must fail, and the correct response is to fix the code rather than
to relax the test.

Three independent mechanisms are checked, because each covers a hole the others
cannot see.

1. **Structural** — the types the pipeline is built on have no demographic
   fields, so there is nothing to filter.
2. **Runtime** — a guard on every input to the feature builder, in case a field
   is added later.
3. **Static** — the scoring packages do not import the module where demographics
   live, so reaching them would require adding an import that does not exist.

The third is the strongest. The first two can be defeated by someone determined
to pass a protected attribute through; the third means using one requires an
addition to the code that is visible in any diff.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from guardmatch.core.exceptions import ProtectedAttributeError
from guardmatch.features.blocklist import (
    BLOCKED_ATTRIBUTES,
    assert_feature_names_clean,
    assert_no_protected_fields,
)
from guardmatch.features.registry import FEATURE_NAMES
from guardmatch.schemas.candidate import ParsedProfile
from guardmatch.schemas.job import Job

pytestmark = pytest.mark.gate

SRC_ROOT = Path(__file__).resolve().parents[1] / "src" / "guardmatch"

# Packages on the scoring path. None of these may reach demographics.
SCORING_PACKAGES = ("features", "parsing", "ranking", "explain", "registry", "api")

# The only module permitted to import demographics, since measuring fairness
# requires them.
PROTECTED_MODULE = "guardmatch.data.protected"


# ---------------------------------------------------------------------------
# Runtime guard
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("attribute", sorted(BLOCKED_ATTRIBUTES))
def test_every_blocked_attribute_is_rejected(attribute: str) -> None:
    """Each blocked name must raise, individually.

    Parametrised rather than looped so a single newly-permitted attribute shows
    up as one named failure instead of hiding inside a passing aggregate.
    """
    with pytest.raises(ProtectedAttributeError):
        assert_no_protected_fields({attribute: "value"}, context="test")


@pytest.mark.parametrize(
    "attribute",
    [
        "Gender",
        "GENDER",
        "candidate_gender",
        "gender_encoded",
        "applicant_age",
        "age_bucket",
        "ethnic_group",
        "home_postcode",
        "full_name",
        "date_of_birth",
    ],
)
def test_disguised_attributes_are_rejected(attribute: str) -> None:
    """Renaming or embedding must not get a protected attribute through."""
    with pytest.raises(ProtectedAttributeError):
        assert_no_protected_fields({attribute: 1}, context="test")


@pytest.mark.parametrize(
    "attribute",
    ["average_score", "trace_id", "coverage", "page_count", "message", "storage_path"],
)
def test_innocent_names_are_not_rejected(attribute: str) -> None:
    """The gate must not fire on names that merely contain 'age' or 'race'.

    A gate that cries wolf gets disabled, which is a slower route to the same
    failure it was built to prevent.
    """
    assert_no_protected_fields({attribute: 1}, context="test")


def test_mixed_payload_reports_every_offender() -> None:
    with pytest.raises(ProtectedAttributeError) as excinfo:
        assert_no_protected_fields(
            {"exp_gap": 2.0, "gender": "f", "nationality": "x"}, context="test"
        )
    message = str(excinfo.value)
    assert "gender" in message
    assert "nationality" in message


# ---------------------------------------------------------------------------
# Structural guarantee
# ---------------------------------------------------------------------------


def test_parsed_profile_carries_no_protected_field() -> None:
    """The type the pipeline is built on has no demographics to filter out."""
    assert_no_protected_fields(
        dict.fromkeys(ParsedProfile.model_fields, 0), context="ParsedProfile"
    )


def test_job_carries_no_protected_field() -> None:
    assert_no_protected_fields(dict.fromkeys(Job.model_fields, 0), context="Job")


def test_feature_contract_is_clean() -> None:
    assert_feature_names_clean(FEATURE_NAMES)


def test_no_feature_name_matches_a_blocked_attribute() -> None:
    assert not (set(FEATURE_NAMES) & BLOCKED_ATTRIBUTES)


# ---------------------------------------------------------------------------
# Static import barrier
# ---------------------------------------------------------------------------


def _imported_modules(path: Path) -> set[str]:
    """Every module name imported by a Python file."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


@pytest.mark.parametrize("package", SCORING_PACKAGES)
def test_scoring_packages_do_not_import_demographics(package: str) -> None:
    """No module on the scoring path may import protected attributes.

    This is the barrier that matters. Using a protected attribute has to require
    *adding* an import that is not there, rather than *forgetting* a filter that
    is — and an added import is visible in every code review.
    """
    offenders: list[str] = []
    for path in (SRC_ROOT / package).rglob("*.py"):
        if PROTECTED_MODULE in _imported_modules(path):
            offenders.append(str(path.relative_to(SRC_ROOT)))

    assert not offenders, (
        f"{package} imports {PROTECTED_MODULE} in {offenders}. Demographics must be "
        f"reachable only from the fairness audit."
    )


def test_fairness_package_may_import_demographics() -> None:
    """The inverse check: the barrier must not be so tight that the audit cannot run.

    A rule that also blocks measurement would leave the system unable to detect
    the very bias the barrier exists to prevent.
    """
    fairness = SRC_ROOT / "fairness"
    assert fairness.exists()

    from guardmatch.data import protected

    assert hasattr(protected, "generate_protected_attributes")


# ---------------------------------------------------------------------------
# The gate must be capable of failing
# ---------------------------------------------------------------------------


def test_gate_actually_fires() -> None:
    """Prove the gate can fail.

    A test that has never failed proves nothing about what it claims to detect.
    This asserts the detection path really does raise when a protected attribute
    is present, so a passing suite is evidence rather than decoration.
    """
    clean = {"exp_gap": 1.0, "licence_match": 1.0}
    assert_no_protected_fields(clean, context="test")

    contaminated = {**clean, "gender": "female"}
    with pytest.raises(ProtectedAttributeError, match="gender"):
        assert_no_protected_fields(contaminated, context="test")
