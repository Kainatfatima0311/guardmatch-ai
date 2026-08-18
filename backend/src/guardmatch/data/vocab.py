"""Surface vocabulary for synthetic CV text.

Every certification, shift pattern and site type is written here in several
forms, because the parser's real job is not extraction — it is *normalisation*.
A human reading "SIA licensed", "holds a valid S.I.A. licence" and "security
licence (SIA)" sees one fact three times. A regex sees three unrelated strings.

If the generator only ever wrote the phrasing the parser was built for, the
parser tests would pass while proving nothing. So the variants below are the
adversary: the generator picks one at random, and the parser has to recover the
canonical code regardless of which one it got.

Two variants per entry are deliberately awkward — abbreviations, punctuation,
and spellings that differ by region — since those are the forms that break a
naive matcher.
"""

from __future__ import annotations

from guardmatch.schemas.enums import CertificationCode, ShiftType, SiteType

# ---------------------------------------------------------------------------
# Certifications
# ---------------------------------------------------------------------------

CERTIFICATION_PHRASINGS: dict[CertificationCode, tuple[str, ...]] = {
    CertificationCode.SECURITY_LICENCE: (
        "SIA licence",
        "SIA license",
        "S.I.A. licensed",
        "security licence",
        "security license",
        "SIA badge",
        "SIA-licensed guard",
        "valid SIA licence (front line)",
    ),
    CertificationCode.FIRST_AID: (
        "first aid",
        "first-aid certified",
        "First Aid at Work",
        "FAW certificate",
        "emergency first aid at work",
        "EFAW",
    ),
    CertificationCode.CPR: (
        "CPR",
        "C.P.R. certified",
        "cardiopulmonary resuscitation",
        "CPR and AED trained",
        "CPR qualified",
    ),
    CertificationCode.FIRE_SAFETY: (
        "fire safety",
        "fire marshal",
        "fire warden",
        "fire safety awareness",
        "fire marshall training",
    ),
    CertificationCode.CCTV_OPERATION: (
        "CCTV",
        "CCTV operation",
        "C.C.T.V. operator",
        "public space surveillance (CCTV)",
        "CCTV monitoring",
        "closed circuit television operation",
    ),
    CertificationCode.CONFLICT_MANAGEMENT: (
        "conflict management",
        "conflict resolution",
        "de-escalation training",
        "physical intervention",
        "conflict management training",
    ),
    CertificationCode.DOG_HANDLING: (
        "dog handling",
        "K9 handling",
        "canine handling",
        "security dog handler",
        "NASDU dog handling",
    ),
    CertificationCode.CLOSE_PROTECTION: (
        "close protection",
        "CP licence",
        "executive protection",
        "close protection officer",
        "bodyguard training",
    ),
    CertificationCode.HEALTH_AND_SAFETY: (
        "health and safety",
        "health & safety",
        "H&S certificate",
        "IOSH Working Safely",
        "health and safety level 2",
    ),
}

# ---------------------------------------------------------------------------
# Shift availability
# ---------------------------------------------------------------------------

SHIFT_PHRASINGS: dict[ShiftType, tuple[str, ...]] = {
    ShiftType.DAY: (
        "day shifts",
        "daytime cover",
        "day duty",
        "days",
    ),
    ShiftType.NIGHT: (
        "night shifts",
        "nights",
        "night duty",
        "overnight cover",
        "nightshift",
    ),
    ShiftType.WEEKEND: (
        "weekends",
        "weekend cover",
        "Saturdays and Sundays",
        "weekend shifts",
    ),
    ShiftType.ROTATING: (
        "rotating shifts",
        "rotating rota",
        "4 on 4 off",
        "shift rotation",
        "rotating pattern",
    ),
}

# ---------------------------------------------------------------------------
# Site types
# ---------------------------------------------------------------------------

SITE_PHRASINGS: dict[SiteType, tuple[str, ...]] = {
    SiteType.RETAIL: (
        "retail",
        "shopping centre",
        "department store",
        "retail park",
        "high street store",
    ),
    SiteType.CORPORATE: (
        "corporate",
        "office building",
        "corporate headquarters",
        "business park",
        "reception and front of house",
    ),
    SiteType.CONSTRUCTION: (
        "construction site",
        "building site",
        "construction",
        "site security",
    ),
    SiteType.EVENT: (
        "event security",
        "concerts and festivals",
        "stadium",
        "large events",
        "crowd control at events",
    ),
    SiteType.RESIDENTIAL: (
        "residential",
        "gated community",
        "apartment complex",
        "residential estate",
    ),
    SiteType.INDUSTRIAL: (
        "industrial",
        "warehouse",
        "distribution centre",
        "manufacturing plant",
        "logistics depot",
    ),
}

# ---------------------------------------------------------------------------
# Job titles
# ---------------------------------------------------------------------------

ROLE_TITLES: tuple[str, ...] = (
    "Security Guard",
    "Security Officer",
    "Static Guard",
    "Mobile Patrol Officer",
    "Door Supervisor",
    "Retail Security Officer",
    "Corporate Security Officer",
    "Night Security Officer",
    "Site Security Officer",
    "Control Room Operator",
)

# ---------------------------------------------------------------------------
# Experience phrasings
# ---------------------------------------------------------------------------

# Each template takes the years value. The word-number and date-range forms are
# the ones a digit-hunting regex misses, which is exactly why they are here.
EXPERIENCE_TEMPLATES: tuple[str, ...] = (
    "{years} years of experience",
    "{years}+ years of experience",
    "over {years} years in the security industry",
    "{years} years' experience in security",
    "approximately {years} years of security experience",
    "{words} years of experience",
    "{start}-{end} ({years} years)",
)

NUMBER_WORDS: dict[int, str] = {
    0: "no",
    1: "one",
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
    11: "eleven",
    12: "twelve",
    15: "fifteen",
    20: "twenty",
}

# ---------------------------------------------------------------------------
# CV structure
# ---------------------------------------------------------------------------

# Section headings vary because real CVs are not written to a schema. A parser
# that keys off exact headings would be brittle in a way these variants expose.
SECTION_HEADINGS: dict[str, tuple[str, ...]] = {
    "summary": ("PROFILE", "SUMMARY", "PERSONAL STATEMENT", "ABOUT ME", "OVERVIEW"),
    "experience": ("EXPERIENCE", "WORK HISTORY", "EMPLOYMENT", "CAREER HISTORY"),
    "certifications": (
        "CERTIFICATIONS",
        "QUALIFICATIONS",
        "LICENCES & TRAINING",
        "TRAINING",
        "CERTIFICATES",
    ),
    "availability": ("AVAILABILITY", "SHIFT AVAILABILITY", "WORKING PATTERN"),
}

SUMMARY_TEMPLATES: tuple[str, ...] = (
    "Reliable {title} with {experience}.",
    "Experienced {title}. {experience}.",
    "{title} with {experience}, seeking a new posting.",
    "Dedicated {title}, {experience}.",
)

DRIVING_PHRASINGS: tuple[str, ...] = (
    "Full clean driving licence",
    "Holds a full UK driving licence",
    "Driving licence: full, clean",
    "Full driving licence held",
)

NO_DRIVING_PHRASINGS: tuple[str, ...] = (
    "No driving licence",
    "Does not drive",
    "Driving licence: none",
)
