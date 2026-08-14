"""CV text to :class:`ParsedProfile`.

The pipeline is loaded once and reused. spaCy model loading takes seconds, which
would be a per-request cost rather than a startup cost if done naively.

Two behaviours are worth stating plainly, because both are fairness decisions
wearing engineering clothes.

**Nothing is defaulted.** When experience cannot be determined the field is
``None``, never ``0``. Defaulting would silently convert a parser failure into a
statement that the candidate has no experience, and the candidate would be
ranked down for our bug. LightGBM handles missing values natively, so passing
``None`` through costs nothing.

**Uncertainty is surfaced, not swallowed.** Anything ambiguous becomes a
``parse_warning``, and warnings travel all the way out to the API response, so a
reviewer can see where the system was unsure rather than receiving a confident
number built on a guess.
"""

from __future__ import annotations

import functools

import spacy
from spacy.language import Language

from guardmatch.core.exceptions import ParsingError
from guardmatch.core.logging import get_logger
from guardmatch.core.metrics import parse_failures_total, parse_warnings_total
from guardmatch.parsing.normalizers import find_shifts, find_sites, match_certification
from guardmatch.parsing.patterns import (
    BULLET_LINE,
    CERT_LABEL,
    EMPLOYMENT_PERIOD,
    EMPLOYMENT_SITE,
    HAS_DRIVING,
    MAX_CV_LENGTH,
    NO_DRIVING,
    NO_PREVIOUS_ROLES,
    NUMERIC_EXPERIENCE,
    SECTION_HEADING,
    WORD_EXPERIENCE,
    WORD_TO_NUMBER,
    build_certification_patterns,
)
from guardmatch.schemas.candidate import Candidate, ParsedProfile
from guardmatch.schemas.enums import CertificationCode

logger = get_logger(__name__)

# The corpus is written against 2026. Recency is measured from here rather than
# from the wall clock, so that a parse of the same CV gives the same answer
# regardless of when it runs — otherwise tests and stored features would drift
# apart over time.
REFERENCE_YEAR = 2026

_EXPERIENCE_SECTIONS = frozenset({"EXPERIENCE", "WORK HISTORY", "EMPLOYMENT", "CAREER HISTORY"})


@functools.lru_cache(maxsize=1)
def get_nlp() -> Language:
    """Load the spaCy pipeline with certification patterns attached.

    Cached, so the model is read from disk once per process.

    Only the tokeniser is needed — the parser, tagger and NER add latency and
    contribute nothing, since matching is done by explicit rules.
    """
    nlp = spacy.load("en_core_web_sm", disable=["parser", "tagger", "ner", "lemmatizer"])
    ruler = nlp.add_pipe("entity_ruler", config={"phrase_matcher_attr": "LOWER"})
    ruler.add_patterns(build_certification_patterns())  # type: ignore[attr-defined]
    return nlp


def _split_sections(text: str) -> dict[str, list[str]]:
    """Group lines under their heading.

    Section membership matters: "stadium" in an employment line is site
    experience, whereas the same word elsewhere is not.
    """
    sections: dict[str, list[str]] = {"": []}
    current = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if SECTION_HEADING.match(line):
            current = line
            sections.setdefault(current, [])
        else:
            sections[current].append(line)
    return sections


def _extract_experience(text: str, warnings: list[str]) -> float | None:
    """Recover years of experience, or ``None``.

    Several statements can appear in one CV. The largest is taken, on the
    reasoning that a summary line states total career length while individual
    role descriptions state fragments of it.
    """
    values: list[float] = [float(match.group(1)) for match in NUMERIC_EXPERIENCE.finditer(text)]

    for match in WORD_EXPERIENCE.finditer(text):
        word = match.group(1).lower()
        if word in WORD_TO_NUMBER:
            values.append(float(WORD_TO_NUMBER[word]))

    if not values:
        warnings.append("years_experience: not stated")
        parse_warnings_total.labels(field="years_experience").inc()
        return None

    return max(values)


def _extract_certifications(
    doc: spacy.tokens.Doc, sections: dict[str, list[str]], warnings: list[str]
) -> frozenset[CertificationCode]:
    """Recover certifications via the entity ruler, then fuzzy-match leftovers.

    The ruler catches known phrasings exactly. Bullet lines that produced no
    entity are then fuzzy-matched, which is where typos are recovered.
    """
    found: set[CertificationCode] = set()

    for entity in doc.ents:
        if entity.label_ == CERT_LABEL and entity.ent_id_:
            found.add(CertificationCode(entity.ent_id_))

    matched_spans = {entity.text.lower() for entity in doc.ents if entity.label_ == CERT_LABEL}

    for lines in sections.values():
        for line in lines:
            bullet = BULLET_LINE.match(line)
            if not bullet:
                continue
            content = bullet.group(1).strip()
            if any(span in content.lower() for span in matched_spans):
                continue
            code = match_certification(content)
            if code is not None:
                found.add(code)
            else:
                warnings.append(f"certification: unrecognised entry {content!r}")
                parse_warnings_total.labels(field="certifications").inc()

    return frozenset(found)


def _extract_employment(
    sections: dict[str, list[str]], warnings: list[str]
) -> tuple[int | None, int | None]:
    """Recover role count and months since the most recent role.

    The count has three outcomes, not two. ``0`` means the CV states there are no
    previous security roles; ``None`` means the CV has no employment section at
    all. Roughly one CV in five omits the section, and reporting that as zero
    roles would turn a formatting choice into a career gap.

    Recency is approximate. The corpus writes year ranges, so a role that ended
    four months ago and one that ended eleven months ago both read as ending in
    the current year. The estimate is therefore coarse by construction rather
    than by defect, and the model sees it as such.
    """
    lines: list[str] = []
    for heading, section_lines in sections.items():
        if heading.upper() in _EXPERIENCE_SECTIONS:
            lines.extend(section_lines)

    if any(NO_PREVIOUS_ROLES.search(line) for line in lines):
        return 0, None

    if not lines:
        warnings.append("employment: no employment section found")
        parse_warnings_total.labels(field="employment").inc()
        return None, None

    periods = [match for line in lines for match in EMPLOYMENT_PERIOD.finditer(line)]
    if not periods:
        warnings.append("employment: section present but no dated roles found")
        parse_warnings_total.labels(field="employment").inc()
        return None, None

    role_count = len(periods)

    end_values = [match.group(2).lower() for match in periods]
    if "present" in end_values:
        return role_count, 0

    latest_end = max(int(value) for value in end_values)
    months = max(0, (REFERENCE_YEAR - latest_end) * 12)
    return role_count, months


def _extract_driving(text: str, warnings: list[str]) -> bool | None:
    """Recover driving licence status, or ``None`` when the CV is silent.

    Three outcomes, not two. ``False`` means the CV states the candidate does not
    drive; ``None`` means driving was never mentioned. Around a third of CVs
    never raise the subject, and collapsing that silence into ``False`` would
    mark a licensed driver as unlicensed because of what they left out.

    Negative patterns are tested first: "No driving licence" contains "driving
    licence", so checking positives first inverts the answer.
    """
    if NO_DRIVING.search(text):
        return False
    if HAS_DRIVING.search(text):
        return True
    warnings.append("driving_licence: not stated")
    parse_warnings_total.labels(field="driving_licence").inc()
    return None


def parse_cv(candidate: Candidate) -> ParsedProfile:
    """Extract a structured profile from a candidate's CV text.

    Args:
        candidate: The application, carrying raw CV text.

    Returns:
        A profile with unextractable fields set to ``None`` and any ambiguity
        recorded in ``parse_warnings``.

    Raises:
        ParsingError: The text is empty or unusably long.
    """
    text = candidate.cv_text.strip()

    if not text:
        parse_failures_total.labels(reason="empty").inc()
        msg = f"empty CV text for candidate {candidate.candidate_id}"
        raise ParsingError(msg)

    if len(text) > MAX_CV_LENGTH:
        parse_failures_total.labels(reason="too_long").inc()
        msg = (
            f"CV text for candidate {candidate.candidate_id} exceeds "
            f"{MAX_CV_LENGTH} characters"
        )
        raise ParsingError(msg)

    warnings: list[str] = []
    sections = _split_sections(text)
    doc = get_nlp()(text)

    years = _extract_experience(text, warnings)
    certifications = _extract_certifications(doc, sections, warnings)
    role_count, months_since_last = _extract_employment(sections, warnings)

    shift_availability = find_shifts(text)
    if not shift_availability:
        warnings.append("shift_availability: not stated")
        parse_warnings_total.labels(field="shift_availability").inc()

    # Only the trailing site portion of each employment line is searched. The
    # rest of the line contains the job title, and titles carry site words --
    # "Retail Security Officer" posted to a stadium would otherwise be credited
    # with retail experience the candidate never had.
    site_fragments = [
        match.group(1)
        for heading, lines in sections.items()
        if heading.upper() in _EXPERIENCE_SECTIONS
        for line in lines
        if (match := EMPLOYMENT_SITE.search(line))
    ]
    site_experience = find_sites("\n".join(site_fragments))

    return ParsedProfile(
        candidate_id=candidate.candidate_id,
        years_experience=years,
        certifications=certifications,
        driving_licence=_extract_driving(text, warnings),
        shift_availability=shift_availability,
        site_experience=site_experience,
        previous_role_count=role_count,
        months_since_last_role=months_since_last,
        parse_warnings=tuple(warnings),
    )
