"""Calendar-based child age calculations shared by profiles and retrieval."""

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import re
from math import isfinite


AGE_SCOPE_MESSAGE = (
    "This service provides baby-care guidance for children from birth through 24 months. "
    "Please ask about a child within this age range."
)

NUMBER_WORDS = dict(zip(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split(),
    range(20), strict=True,
))
NUMBER_WORDS.update(dict(zip(
    "twenty thirty forty fifty sixty seventy eighty ninety".split(), range(20, 100, 10), strict=True,
)))
_SMALL_NUMBER = "(?:" + "|".join(list(NUMBER_WORDS)[:20]) + ")"
_TENS = r"(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)(?:[ -]+(?:one|two|three|four|five|six|seven|eight|nine))?"
_HUNDREDS = rf"(?:one|two|three|four|five|six|seven|eight|nine)[ -]+hundred(?:[ -]+(?:and[ -]+)?(?:{_TENS}|{_SMALL_NUMBER}))?"
_NUMBER = rf"(?:\d+(?:\.\d+)?|{_HUNDREDS}|{_TENS}|{_SMALL_NUMBER})(?:[ -]+and[ -]+a[ -]+half)?"
AGE_QUANTITY = re.compile(rf"\b({_NUMBER}|half(?:[ -]+a)?|an?)[ -]*(days?|weeks?|months?|years?)\b", re.I)
_DIGIT_QUANTITY = r"\d+(?:\.\d+)?\s+(?:days?|weeks?|months?|years?)\b"
_COMPOUND_AGE = re.compile(rf"\b{_DIGIT_QUANTITY}(?:\s*(?:and|-)\s*{_DIGIT_QUANTITY})+", re.I)
_AGE_SCALE = {"day": 1 / 30.4375, "week": 7 / 30.4375, "month": 1, "year": 12}


def normalize_age_expressions(message: str) -> str:
    """Normalize quantities beside age units only; keep the stored message intact."""
    def replace(match):
        raw, unit = match.groups()
        raw = raw.lower()
        if raw in {"a", "an"}:
            return f"1 {unit}"
        if re.fullmatch(r"half(?:[ -]+a)?", raw):
            return f"0.5 {unit}"
        half = re.search(r"[ -]+and[ -]+a[ -]+half$", raw)
        if half:
            raw = raw[:half.start()]
        if raw[0].isdigit():
            return f"{float(raw) + 0.5:g} {unit}" if half else f"{raw} {unit}"
        number = 0
        for word in re.split(r"[ -]+", raw.lower()):
            if word == "hundred":
                number *= 100
            elif word != "and":
                number += NUMBER_WORDS[word]
        return f"{number + (0.5 if half else 0):g} {unit}"

    message = re.sub(r"[\u2010-\u2014\u2212]", "-", message)
    normalized = AGE_QUANTITY.sub(replace, message)
    normalized = re.sub(r"\b(he|she)['\u2019]s\s+", r"\1 is ", normalized, flags=re.I)
    normalized = re.sub(r"\bi['\u2019]m\s+", "I am ", normalized, flags=re.I)
    normalized = re.sub(r"\b(we|they)['\u2019]re\s+", r"\1 are ", normalized, flags=re.I)

    def singular_age(match):
        prefix, suffix = normalized[:match.start()], normalized[match.end():]
        # English singular age modifiers imply one unit: "my month-old baby".
        # Restrict this to child descriptions so a month-old toy is not an age.
        if re.search(r"\b\d+(?:\.\d+)?[ -]*$|\b(?:few|several|many|some)[ -]*$|[?_]\s*$", prefix, re.I):
            return match.group()
        child_after = re.match(rf"[ -]+{CHILD_SUBJECT}\b", suffix, re.I)
        child_before = re.search(
            rf"\b(?:{CHILD_SUBJECT}|he|she|they)\s+(?:{AGE_STATE}\s+)?"
            r"(?:(?:about|around|roughly|approximately|almost|nearly)\s+)?$", prefix, re.I,
        )
        standalone = not suffix.strip(" .!?,;:") and (
            not prefix.strip() or re.search(r"\b(?:my|our|your|his|her|their)\s*$", prefix, re.I)
        )
        if child_after or child_before or standalone:
            return "1 " + match.group()
        return match.group()

    normalized = re.sub(r"\b(day|week|month|year)[ -]+old\b", singular_age, normalized, flags=re.I)

    def compound(match):
        quantities = AGE_QUANTITY.findall(match.group())
        scales = [_AGE_SCALE[unit.lower().rstrip("s")] for _, unit in quantities]
        # Combine one age only in descending units; not lists of children's ages.
        if any(first <= second for first, second in zip(scales, scales[1:])):
            return match.group()
        total = sum(float(raw) * scale for (raw, _), scale in zip(quantities, scales, strict=True))
        return f"{total:g} months" if isfinite(total) else match.group()

    return _COMPOUND_AGE.sub(compound, normalized)


CHILD_SUBJECT = r"(?:baby|child|infant|toddler|daughter|son|little (?:girl|boy|one))"
AGE_STATE = r"(?:(?:is|are)(?:\s+(?:now|just|already))?|aged?|turning|(?:(?:has|have)\s+)?(?:(?:just|recently)\s+)?turned)"
MESSAGE_AGE = re.compile(
    rf"\b(?:(?:(?:(?:my|our|the|a)\s+)?{CHILD_SUBJECT}"
    r"(?:\s+(?:(?:named|called)\s+)?[^\W\d_][\w'’-]*(?:\s+[^\W\d_][\w'’-]*){0,2}?(?=\s+(?:is|aged?|turning)\s))?"
    rf"\s+(?:{AGE_STATE}\s+)?|"
    rf"(?:he|she|they|another)\s+{AGE_STATE}\s+|"
    r"(?:aged?|at)\s+)(\d+(?:\.\d+)?)\s*[- ]?(days?|weeks?|months?|years?)\b|"
    r"(\d+(?:\.\d+)?)\s*[- ]?(days?|weeks?|months?|years?)\s*[- ]old\b)", re.I,
)


def age_correction_months(message: str) -> float | None:
    """Read a complete correction, excluding the explicitly rejected old age."""
    quantity = r"\d+(?:\.\d+)?\s*[- ]?(?:days?|weeks?|months?|years?)(?:[- ]old)?"
    match = re.fullmatch(
        rf"(?:(?:no|sorry)[, ]+)*(?:i meant|actually|correction)[, ]*"
        rf"(?:(?:he|she|they|(?:my|our|the) {CHILD_SUBJECT}) (?:is|are) )?"
        rf"(?P<age>{quantity})(?:,?\s+not\s+{quantity})?",
        normalize_age_expressions(message).strip().rstrip(".!?"), re.I,
    )
    if match:
        number, unit = AGE_QUANTITY.search(match["age"]).groups()
        months = float(number) * _AGE_SCALE[unit.lower().rstrip("s")]
        return months if isfinite(months) else None
    return None


def _noncurrent_age(message: str, start: int) -> bool:
    # Attribute an age to its clause: a reported example or past/future age is
    # not the child's current age. Contrast clauses can state the actual age.
    prefix = re.split(r"(?<!\d)\.(?!\d)|[!?;\n]|\b(?:but|whereas)\b", message[:start], flags=re.I)[-1]
    return bool(re.search(
        r"\b(?:not|isn['\u2019]t|aren['\u2019]t)\s+(?:an?\s+)?$|"
        r"\b(?:was|were)\s+(?:an?\s+)?$|"
        r"\b(?:leaflet|handout|article|book|guide|website|video|example)\b[^.!?;]*"
        r"\b(?:says?|said|describes?|mentions?|shows?|suggests?|for|about)\b|"
        r"\b(?:will be|will turn|used to be|when (?:he|she|they|my child) (?:was|were))\b",
        prefix, re.I,
    ))


def _adult_age(message: str, start: int, end: int) -> bool:
    """Exclude an age explicitly attached to a caregiver rather than the child."""
    prefix = re.split(r"[.!?;\n]", message[:start])[-1]
    adult = r"(?:mother|father|mum|mom|dad|parent|partner|husband|wife|grandmother|grandfather|aunt|uncle|caregiver)"
    return bool(re.search(
        rf"\b(?:i\s+am|we\s+are|(?:my|our|the|his|her|their|your)\s+{adult}\s+(?:is|was|aged?))"
        r"\s+(?:(?:now|currently|already)\s+)?(?:an?\s+)?$", prefix, re.I,
    ) or re.match(rf"\s+{adult}\b", message[end:], re.I))


@dataclass(frozen=True)
class MessageAge:
    months: float | None = None
    needs_clarification: bool = False
    incomplete: bool = False


def _incomplete_child_age(message: str) -> bool:
    """Recognise an age-shaped child phrase with its quantity missing."""
    pattern = rf"\b(?:days?|weeks?|months?|years?)[ -]+(?:(?:old[ -]+)?(?P<child>{CHILD_SUBJECT})\b|old\b)"
    for match in re.finditer(pattern, message, re.I):
        prefix = message[:match.start()]
        # Complete word quantities have already been normalised to digits.
        if re.search(r"\b\d+(?:\.\d+)?[ -]*$", prefix):
            continue
        if _noncurrent_age(message, match.start()) or _adult_age(message, match.start(), match.end()):
            continue
        predicate = re.search(
            rf"\b(?:{CHILD_SUBJECT}(?:\s+(?:named|called)\s+[^\W\d_][\w'-]*)?|he|she|they)"
            rf"\s+(?:{AGE_STATE}\s+)?"
            r"(?:(?:about|around|roughly|approximately|almost|nearly)\s+)?$", prefix, re.I,
        )
        if match["child"] or predicate or (not prefix.strip() and not message[match.end():].strip(" .!?")):
            return True
    return False


def inspect_message_age(message: str) -> MessageAge:
    """Distinguish a missing age from an incomplete or conflicting child age."""
    ages = set()
    subject_ages = set()
    message = normalize_age_expressions(message)
    correction = age_correction_months(message)
    if correction is not None:
        return MessageAge(correction)
    if _incomplete_child_age(message):
        return MessageAge(needs_clarification=True, incomplete=True)
    for match in MESSAGE_AGE.finditer(message):
        if (_noncurrent_age(message, match.start())
                or match.group(3) and _adult_age(message, match.start(), match.end())):
            continue
        number, unit = (match.group(1), match.group(2)) if match.group(1) else (match.group(3), match.group(4))
        scale = _AGE_SCALE[unit.lower().rstrip("s")]
        months = float(number) * scale
        if isfinite(months):
            ages.add(months)
            prefix = message[max(0, match.start() - 12):match.start()]
            if (match.group(1) and re.search(rf"\b(?:{CHILD_SUBJECT}|he|she|they|another)\b", match.group(), re.I)
                    or match.group(3) and re.match(rf"[ -]+{CHILD_SUBJECT}\b", message[match.end():], re.I)
                    or re.search(r"\b(?:my|our|your)\s*$", prefix, re.I)):
                subject_ages.add(months)
    # Attribute forms such as "my one-day baby" do not need the word "old".
    for match in re.finditer(r"\b(\d+(?:\.\d+)?)\s+(days?|weeks?|months?|years?)[ -]+(?:baby|child|infant|toddler|daughter|son)\b", message, re.I):
        if _noncurrent_age(message, match.start()):
            continue
        number, unit = match.groups()
        months = float(number) * {"day": 1 / 30.4375, "week": 7 / 30.4375, "month": 1, "year": 12}[unit.lower().rstrip("s")]
        if isfinite(months):
            ages.add(months)
            subject_ages.add(months)
    for match in re.finditer(r"\b(?:my|our|the|a|your)\s+new[ -]?born(?:\s+(?:baby|child|infant))?\b", message, re.I):
        if not _noncurrent_age(message, match.start()):
            ages.add(0)
            subject_ages.add(0)
    selected = subject_ages or ages
    if len(selected) == 1:
        return MessageAge(selected.pop())
    return MessageAge(needs_clarification=len(selected) > 1)


def message_age_months(message: str) -> float | None:
    """Return a single resolved age for callers that do not choose a response."""
    return inspect_message_age(message).months


def age_from_user_quote(quote: str, message: str) -> float | None:
    """Validate an exact quote in its original clause, excluding reported ages."""
    if not quote or quote not in message:
        return None
    normalized, normalized_quote = normalize_age_expressions(message), normalize_age_expressions(quote)
    start = normalized.find(normalized_quote)
    if start < 0 or _noncurrent_age(normalized, start) or _adult_age(normalized, start, start + len(normalized_quote)):
        return None
    return message_age_months(quote)


def current_date() -> date:
    return datetime.now(timezone(timedelta(hours=3))).date()


def add_months(birth_date: date, months: int) -> date:
    """Use the last day of a shorter month for birthdays such as January 31."""
    year, month_index = divmod(birth_date.year * 12 + birth_date.month - 1 + months, 12)
    month = month_index + 1
    return date(year, month, min(birth_date.day, monthrange(year, month)[1]))


def within_project_scope(birth_date: date, today: date | None = None) -> bool:
    """Birth through the calendar second birthday, inclusive; no fixed day count."""
    today = today or current_date()
    return birth_date <= today <= add_months(birth_date, 24)


def age_details(birth_date: date, today: date | None = None) -> tuple[int, int, float]:
    """Return exact days, completed calendar months, and a fractional display age."""
    today = today or current_date()
    if birth_date > today:
        raise ValueError("Date of birth cannot be in the future.")
    months = (today.year - birth_date.year) * 12 + today.month - birth_date.month
    if today < add_months(birth_date, months):
        months -= 1
    start, end = add_months(birth_date, months), add_months(birth_date, months + 1)
    fraction = (today - start).days / (end - start).days
    return (today - birth_date).days, months, months + fraction
