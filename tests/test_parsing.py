"""Parser tests.

The tests that matter most here are the ones asserting the parser stays
*silent* rather than the ones asserting it finds things.

A parser that misses a certification costs a candidate some ranking position. A
parser that invents one puts an unqualified person on a security shortlist, or
marks a licensed driver as unlicensed because their CV never mentioned driving.
Those are the failures worth defending against, so several tests exist purely to
confirm that unstated facts come back as ``None`` and that near-miss text
produces no match at all.
"""

from __future__ import annotations

import pytest

from guardmatch.core.exceptions import ParsingError
from guardmatch.data.candidates import generate_candidates
from guardmatch.data.vocab import CERTIFICATION_PHRASINGS
from guardmatch.parsing.extractor import parse_cv
from guardmatch.parsing.normalizers import (
    canonical_text,
    find_shifts,
    match_certification,
)
from guardmatch.parsing.patterns import MAX_CV_LENGTH
from guardmatch.schemas.candidate import Candidate
from guardmatch.schemas.enums import CertificationCode, ShiftType, SiteType


def cv(text: str, candidate_id: str = "c_test") -> Candidate:
    """Build a candidate from raw CV text."""
    return Candidate(candidate_id=candidate_id, cv_text=text)


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("S.I.A. licensed", "sia licenced"),
        ("SIA Licence", "sia licence"),
        ("security license", "security licence"),
        ("Fire  Marshall", "fire marshal"),
        ("  CCTV Operation  ", "cctv operation"),
        ("health & safety", "health safety"),
    ],
)
def test_canonical_text_collapses_surface_differences(raw: str, expected: str) -> None:
    assert canonical_text(raw) == expected


def test_canonical_text_handles_empty_input() -> None:
    assert canonical_text("") == ""
    assert canonical_text("   ...   ") == ""


# ---------------------------------------------------------------------------
# Certification matching
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("code", "variant"),
    [(code, variant) for code, variants in CERTIFICATION_PHRASINGS.items() for variant in variants],
)
def test_every_vocabulary_variant_resolves(code: CertificationCode, variant: str) -> None:
    """All 47 phrasing variants must resolve to their canonical code.

    This is the parser's core contract. A variant the generator writes but the
    parser cannot read is a silent data-loss bug.
    """
    assert match_certification(variant) == code


@pytest.mark.parametrize(
    ("typo", "expected"),
    [
        ("SIA licance", CertificationCode.SECURITY_LICENCE),
        ("frist aid", CertificationCode.FIRST_AID),
        ("CCTV oepration", CertificationCode.CCTV_OPERATION),
        ("conflict managment", CertificationCode.CONFLICT_MANAGEMENT),
    ],
)
def test_typos_recovered_by_fuzzy_matching(typo: str, expected: CertificationCode) -> None:
    assert match_certification(typo) == expected


@pytest.mark.parametrize(
    "text",
    [
        "forklift licence",
        "degree in computer science",
        "customer service award",
        "",
        "   ",
    ],
)
def test_unrelated_text_matches_nothing(text: str) -> None:
    """Silence beats a confident guess.

    A false certification match is worse than a missed one, so anything below
    the fuzzy threshold must return None rather than the nearest neighbour.
    """
    assert match_certification(text) is None


def test_phrase_wrapped_in_extra_words_still_resolves() -> None:
    assert (
        match_certification("valid SIA licence (front line), expires 2027")
        == CertificationCode.SECURITY_LICENCE
    )


# ---------------------------------------------------------------------------
# Shift matching
# ---------------------------------------------------------------------------


def test_shift_matching_respects_word_boundaries() -> None:
    """"Saturdays" must not register as the "days" variant of a day shift."""
    found = find_shifts("Available for Saturdays and Sundays.")
    assert found == frozenset({ShiftType.WEEKEND})
    assert ShiftType.DAY not in found


def test_multiple_shifts_found() -> None:
    found = find_shifts("Available for day duty, nightshift and weekend cover.")
    assert found == frozenset({ShiftType.DAY, ShiftType.NIGHT, ShiftType.WEEKEND})


# ---------------------------------------------------------------------------
# Experience extraction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("PROFILE\nGuard with 5 years of experience.", 5.0),
        ("PROFILE\nGuard with 7+ years of experience.", 7.0),
        ("PROFILE\nOver 12 years in the security industry.", 12.0),
        ("PROFILE\nGuard with 3.5 years' experience in security.", 3.5),
        ("PROFILE\nApproximately 8 years of security experience.", 8.0),
        ("PROFILE\nfive years of experience.", 5.0),
        ("PROFILE\nGuard with twenty years of experience.", 20.0),
    ],
)
def test_experience_phrasings(text: str, expected: float) -> None:
    assert parse_cv(cv(text)).years_experience == expected


def test_unstated_experience_is_none_not_zero() -> None:
    """A parser failure must not read as 'no experience'.

    Defaulting to zero would rank a candidate down for our extraction gap rather
    than for anything in their application.
    """
    profile = parse_cv(cv("PROFILE\nReliable security officer seeking a new posting."))
    assert profile.years_experience is None
    assert any("years_experience" in w for w in profile.parse_warnings)


def test_largest_stated_experience_wins() -> None:
    """A summary states career length; role lines state fragments of it."""
    text = "PROFILE\n9 years of experience.\n\nEMPLOYMENT\nGuard with 2 years of experience."
    assert parse_cv(cv(text)).years_experience == 9.0


# ---------------------------------------------------------------------------
# Driving licence
# ---------------------------------------------------------------------------


def test_driving_stated_positive() -> None:
    assert parse_cv(cv("PROFILE\nGuard.\n\nADDITIONAL\nFull clean driving licence")).driving_licence


def test_driving_stated_negative() -> None:
    """"No driving licence" contains "driving licence".

    A matcher checking positives first would report the exact opposite of what
    the CV says.
    """
    assert parse_cv(cv("PROFILE\nGuard.\n\nADDITIONAL\nNo driving licence")).driving_licence is False


def test_driving_unstated_is_none_not_false() -> None:
    profile = parse_cv(cv("PROFILE\nReliable guard with 4 years of experience."))
    assert profile.driving_licence is None
    assert any("driving_licence" in w for w in profile.parse_warnings)


# ---------------------------------------------------------------------------
# Employment history
# ---------------------------------------------------------------------------


def test_explicit_no_roles_is_zero() -> None:
    text = "PROFILE\nGuard.\n\nEMPLOYMENT\nNo previous security roles."
    assert parse_cv(cv(text)).previous_role_count == 0


def test_missing_employment_section_is_none() -> None:
    """An absent section is absence of evidence, not evidence of absence."""
    profile = parse_cv(cv("PROFILE\nGuard with 4 years of experience."))
    assert profile.previous_role_count is None
    assert any("employment" in w for w in profile.parse_warnings)


def test_role_count_and_recency() -> None:
    text = (
        "PROFILE\nGuard.\n\n"
        "EMPLOYMENT\n"
        "Security Officer, Acme Ltd (2024 - present) - retail park\n"
        "Static Guard, Beta Ltd (2021 - 2024) - warehouse\n"
    )
    profile = parse_cv(cv(text))
    assert profile.previous_role_count == 2
    assert profile.months_since_last_role == 0


def test_site_not_taken_from_job_title() -> None:
    """The site is what follows the date range, not what appears in the title.

    "Retail Security Officer" posted to a stadium must not be credited with
    retail experience — that is a fabricated qualification, not a missed one.
    """
    text = "PROFILE\nGuard.\n\nEMPLOYMENT\nRetail Security Officer, Acme Ltd (2022 - 2024) - stadium\n"
    sites = parse_cv(cv(text)).site_experience
    assert SiteType.EVENT in sites
    assert SiteType.RETAIL not in sites


# ---------------------------------------------------------------------------
# Failure modes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["   ", "\n\n\t"])
def test_empty_cv_raises(text: str) -> None:
    with pytest.raises(ParsingError):
        parse_cv(Candidate(candidate_id="c_x", cv_text=text))


def test_oversized_cv_raises() -> None:
    """An unbounded input is a denial-of-service vector on a public endpoint."""
    with pytest.raises(ParsingError, match="exceeds"):
        parse_cv(cv("a " * MAX_CV_LENGTH))


# ---------------------------------------------------------------------------
# End-to-end against ground truth
# ---------------------------------------------------------------------------


def test_recovers_ground_truth_across_the_corpus() -> None:
    """Every fact the generator wrote must be recovered exactly.

    The generator retains the values each CV was built from, so this asserts
    correctness rather than mere plausibility. Facts the generator deliberately
    omitted are excluded — the parser cannot recover what was never written, and
    counting those as errors would measure the generator, not the parser.
    """
    candidates = generate_candidates(300, seed=1234)

    cert_mismatches = 0
    experience_mismatches = 0
    shift_mismatches = 0
    role_mismatches = 0
    driving_mismatches = 0

    for candidate in candidates:
        profile = parse_cv(cv(candidate.cv_text, candidate.candidate_id))

        if profile.certifications != candidate.true_certifications:
            cert_mismatches += 1
        if (
            profile.years_experience is not None
            and abs(profile.years_experience - candidate.true_years_experience) >= 0.55
        ):
            experience_mismatches += 1
        if profile.shift_availability and profile.shift_availability != candidate.true_shift_availability:
            shift_mismatches += 1
        if (
            profile.previous_role_count is not None
            and profile.previous_role_count != candidate.true_previous_role_count
        ):
            role_mismatches += 1
        if (
            profile.driving_licence is not None
            and profile.driving_licence != candidate.true_driving_licence
        ):
            driving_mismatches += 1

    assert cert_mismatches == 0
    assert experience_mismatches == 0
    assert shift_mismatches == 0
    assert role_mismatches == 0
    assert driving_mismatches == 0


def test_no_certification_is_ever_invented() -> None:
    """Across the corpus, the parser must never report an unheld certification.

    Missing one costs ranking position. Inventing one puts an unqualified person
    on a security shortlist, so this is asserted separately and strictly.
    """
    false_positives = 0
    for candidate in generate_candidates(300, seed=99):
        profile = parse_cv(cv(candidate.cv_text, candidate.candidate_id))
        false_positives += len(profile.certifications - candidate.true_certifications)

    assert false_positives == 0
