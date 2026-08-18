"""Extraction patterns.

Two mechanisms, chosen per job rather than by preference.

**spaCy ``EntityRuler``** handles certifications. Every pattern is built from the
vocabulary and carries an ``id``, so a match is traceable to the exact phrase
that produced it. That traceability is the reason for using a rule-based matcher
in a hiring system at all: "this candidate holds a first-aid certificate because
the phrase 'FAW certificate' appeared" is an answer that survives an audit, in a
way that a similarity score does not.

**Regular expressions** handle the numeric and structural facts — durations,
date ranges, employment lines — where a phrase list would be infinite.

The negative driving patterns are checked before the positive ones on purpose.
"No driving licence" contains "driving licence", so a positive-first matcher
records the exact opposite of what the CV says.
"""

from __future__ import annotations

import re

from guardmatch.data.vocab import CERTIFICATION_PHRASINGS, NUMBER_WORDS

CERT_LABEL = "GM_CERT"


def build_certification_patterns() -> list[dict[str, str]]:
    """Build EntityRuler patterns for every certification phrasing.

    Matching is case-insensitive via the ruler's ``phrase_matcher_attr``, so the
    variants are written once here rather than in every casing.
    """
    patterns: list[dict[str, str]] = []
    for code, variants in CERTIFICATION_PHRASINGS.items():
        for variant in variants:
            patterns.append({"label": CERT_LABEL, "pattern": variant, "id": code.value})
    return patterns


# ---------------------------------------------------------------------------
# Experience
# ---------------------------------------------------------------------------

# "5 years", "5+ years", "3.5 years'", "over 12 years"
#
# The curly apostrophe in the pattern is intentional and not interchangeable
# with the straight one: word processors substitute it automatically, so real
# CVs contain both, and an ASCII-only pattern would miss the substituted form.
NUMERIC_EXPERIENCE = re.compile(
    r"(?:over|approximately|about|around)?\s*"
    r"(\d{1,2}(?:\.\d)?)\s*\+?\s*"
    r"years?['’]?\s*(?:of\s+)?(?:security\s+)?(?:experience|in\s+the\s+security|in\s+security)",  # noqa: RUF001
    re.IGNORECASE,
)

# "five years of experience" — the form a digit-hunting regex misses entirely.
_WORD_ALTERNATION = "|".join(sorted(NUMBER_WORDS.values(), key=len, reverse=True))
WORD_EXPERIENCE = re.compile(
    rf"\b({_WORD_ALTERNATION})\s+years?\s+(?:of\s+)?(?:security\s+)?experience",
    re.IGNORECASE,
)

WORD_TO_NUMBER: dict[str, int] = {word: number for number, word in NUMBER_WORDS.items()}

# ---------------------------------------------------------------------------
# Employment history
# ---------------------------------------------------------------------------

# "Security Officer, Acme Ltd (2022 - 2024) - retail"
# "Control Room Operator, Acme Ltd (2024 - present) - stadium"
# The en dash is intentional alongside the hyphen — date ranges are commonly
# typed with either, and CVs written in Word usually carry the en dash.
EMPLOYMENT_PERIOD = re.compile(
    r"\((\d{4})\s*[-–]\s*(present|\d{4})\)",  # noqa: RUF001
    re.IGNORECASE,
)

NO_PREVIOUS_ROLES = re.compile(r"no\s+previous\s+security\s+roles", re.IGNORECASE)

# The site sits after the closing bracket: "... (2022 - 2024) - stadium".
#
# Scoped tightly on purpose. Searching the whole line for site keywords picks up
# words from the job title instead — "Retail Security Officer ... - stadium"
# would credit the candidate with retail experience they do not have, which is a
# fabricated qualification rather than a missed one.
EMPLOYMENT_SITE = re.compile(r"\)\s*[-–]\s*(.+)$")  # noqa: RUF001

# ---------------------------------------------------------------------------
# Driving licence
# ---------------------------------------------------------------------------

# Checked first. Order matters: "No driving licence" contains "driving licence".
NO_DRIVING = re.compile(
    r"(?:no\s+driving\s+licence|does\s+not\s+drive|driving\s+licence\s*:\s*none)",
    re.IGNORECASE,
)

HAS_DRIVING = re.compile(
    r"(?:full[\w\s]*driving\s+licence|driving\s+licence\s*:\s*full|holds\s+a\s+full)",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Section detection
# ---------------------------------------------------------------------------

# Headings are upper case and short. Used to attribute bullet lines to the right
# section, since a site name in the employment history means something different
# from the same word in a certifications list.
SECTION_HEADING = re.compile(r"^[A-Z][A-Z &]{2,}$")

BULLET_LINE = re.compile(r"^\s*[-•*]\s*(.+)$")

# CV text is capped before parsing. An unbounded input is a denial-of-service
# vector on a public endpoint, and no legitimate guard CV approaches this size.
MAX_CV_LENGTH = 20_000
