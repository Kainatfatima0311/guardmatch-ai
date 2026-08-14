"""Mapping every surface form of a fact onto one canonical code.

The parser's hard problem is not finding text — it is deciding that "SIA
licensed", "holds a valid S.I.A. licence" and "security licence (SIA)" are the
same fact. A human sees one thing three times; a naive matcher sees three
unrelated strings.

Three layers handle this, cheapest first.

**Canonicalisation** strips the differences that never carry meaning: case,
periods inside acronyms, British versus American spelling, and extra whitespace.
This alone collapses most variants.

**Exact lookup** against the canonicalised vocabulary. Fast, and every match is
traceable to a specific known phrase.

**Fuzzy matching** as a last resort, for typos. It is deliberately last and
deliberately strict, because a false certification match is worse than a missed
one: claiming a candidate holds a licence they do not hold is a defect that
propagates all the way to a hiring shortlist. When the fuzzy score falls below
threshold, the parser records nothing and notes a warning. Silence beats a
confident guess.
"""

from __future__ import annotations

import re

from rapidfuzz import fuzz, process

from guardmatch.data.vocab import CERTIFICATION_PHRASINGS, SHIFT_PHRASINGS, SITE_PHRASINGS
from guardmatch.schemas.enums import CertificationCode, ShiftType, SiteType

# Minimum similarity for a fuzzy match, on rapidfuzz's 0-100 scale.
#
# Set high on purpose. At 80 the matcher starts confusing "fire safety" with
# "fire marshal" — related but distinct certifications. Missing a real
# certification costs a candidate some ranking position; inventing one that does
# not exist puts an unqualified person on a security shortlist.
FUZZY_THRESHOLD = 88

# Spelling pairs that differ by region but never by meaning.
_SPELLING_EQUIVALENTS: tuple[tuple[str, str], ...] = (
    ("license", "licence"),
    ("licensed", "licenced"),
    ("marshall", "marshal"),
    ("center", "centre"),
    ("organisation", "organization"),
)

_ACRONYM_DOTS = re.compile(r"\b(?:[a-z]\.){2,}[a-z]?\.?")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def canonical_text(text: str) -> str:
    """Reduce a phrase to the form used for lookup.

    Lowercases, collapses dotted acronyms ("s.i.a." to "sia"), unifies regional
    spellings, and squeezes everything else down to single-spaced alphanumerics.
    """
    lowered = text.lower()

    # "s.i.a." -> "sia", before punctuation is stripped generally, so the letters
    # stay joined rather than becoming three separate tokens.
    lowered = _ACRONYM_DOTS.sub(lambda m: m.group(0).replace(".", ""), lowered)

    for variant, canonical in _SPELLING_EQUIVALENTS:
        lowered = lowered.replace(variant, canonical)

    return _NON_ALNUM.sub(" ", lowered).strip()


def _build_lookup[T](phrasings: dict[T, tuple[str, ...]]) -> dict[str, T]:
    """Invert a code-to-variants mapping into variant-to-code."""
    lookup: dict[str, T] = {}
    for code, variants in phrasings.items():
        for variant in variants:
            lookup[canonical_text(variant)] = code
    return lookup


CERTIFICATION_LOOKUP: dict[str, CertificationCode] = _build_lookup(CERTIFICATION_PHRASINGS)
SHIFT_LOOKUP: dict[str, ShiftType] = _build_lookup(SHIFT_PHRASINGS)
SITE_LOOKUP: dict[str, SiteType] = _build_lookup(SITE_PHRASINGS)


def match_certification(phrase: str) -> CertificationCode | None:
    """Resolve a phrase to a certification code, or ``None``.

    Tries exact canonical lookup, then containment, then fuzzy matching. Returns
    ``None`` rather than a best guess when nothing clears the threshold.
    """
    canonical = canonical_text(phrase)
    if not canonical:
        return None

    if canonical in CERTIFICATION_LOOKUP:
        return CERTIFICATION_LOOKUP[canonical]

    # A bullet line often wraps the phrase in extra words: "valid SIA licence
    # (front line)" contains "sia licence". Prefer the longest containment match,
    # so "close protection officer" is not resolved by a shorter unrelated key.
    contained = [key for key in CERTIFICATION_LOOKUP if key in canonical]
    if contained:
        return CERTIFICATION_LOOKUP[max(contained, key=len)]

    result = process.extractOne(
        canonical,
        CERTIFICATION_LOOKUP.keys(),
        scorer=fuzz.WRatio,
        score_cutoff=FUZZY_THRESHOLD,
    )
    if result is None:
        return None
    return CERTIFICATION_LOOKUP[result[0]]


def find_shifts(text: str) -> frozenset[ShiftType]:
    """Find every shift pattern mentioned in ``text``.

    Matched on word boundaries against the canonicalised text, so "days" does
    not fire inside "Saturdays".
    """
    canonical = canonical_text(text)
    found: set[ShiftType] = set()
    for phrase, shift in SHIFT_LOOKUP.items():
        if re.search(rf"\b{re.escape(phrase)}\b", canonical):
            found.add(shift)
    return frozenset(found)


def find_sites(text: str) -> frozenset[SiteType]:
    """Find every site type mentioned in ``text``."""
    canonical = canonical_text(text)
    found: set[SiteType] = set()
    for phrase, site in SITE_LOOKUP.items():
        if re.search(rf"\b{re.escape(phrase)}\b", canonical):
            found.add(site)
    return frozenset(found)
