"""Local English-input gate; language identification is not clinical triage."""

from functools import lru_cache
import re
import unicodedata

from lingua import Language, LanguageDetectorBuilder


LANGUAGE_MESSAGE = (
    "LittleCare can currently check safety and answer only in English. "
    "Please write or record your whole message in English. If you need urgent help, "
    "contact a health professional or local emergency services without waiting for this app.\n\n"
    "Kwa sasa LittleCare inaweza kukagua usalama na kujibu kwa Kiingereza pekee. "
    "Tafadhali andika au rekodi ujumbe wako wote kwa Kiingereza. Ikiwa unahitaji msaada "
    "wa haraka, wasiliana na mtaalamu wa afya au huduma za dharura bila kusubiri programu hii."
)

# Whole-message exceptions only: short acknowledgements and age-clarification
# replies are too ambiguous for statistical language identification.
SHORT_ENGLISH = frozenset({
    "hi", "hello", "hey", "yes", "no", "ok", "okay", "thanks", "thank you",
    "yes please", "no thanks", "no thank you", "please", "help", "more",
    "play", "feeding", "sleep", "soothing", "teething",
    "bcg", "opv", "ipv", "dtp", "dpt", "pcv", "mr", "hpv", "rota",
})
AGE_ONLY = re.compile(r"\d{1,3}(?:\.\d+)?(?:\s*(?:days?|weeks?|months?|years?)(?:\s+old)?)?")
# A whole-message classifier can label code-switched text English. These narrow
# Kiswahili markers also reject common mixed caregiver wording. This list is
# neither a translation service nor a complete code-switching detector.
SWAHILI_MARKERS = frozenset({
    "mtoto", "watoto", "wangu", "mwanangu", "analia", "hapumui", "homa",
    "anatapika", "ameanguka", "anaumwa", "anakataa", "ananyonya", "maziwa",
    "msaada", "nifanye", "ninahitaji", "nisaidie", "sijui", "amekataa", "kulala",
})
WORDS = re.compile(r"[^\W\d_]+", re.UNICODE)


@lru_cache(maxsize=1)
def language_detector():
    # Models are bundled in the pinned wheel. No input or model download leaves
    # the process. Cache the detector, never caregiver text or its decisions.
    return LanguageDetectorBuilder.from_all_spoken_languages().build()


@lru_cache(maxsize=1)
def english_detector():
    return LanguageDetectorBuilder.from_languages(Language.ENGLISH).build()


def _language(detector, text: str):
    values = detector.compute_language_confidence_values(text)
    # Relative separation handles short English messages without interpreting a
    # language likelihood as a safety confidence or requiring long sentences.
    if len(values) < 2 or values[0].value <= 0:
        return None
    # Closely related languages can outrank short English text by a tiny margin.
    # Resolve only a near-tie with a separate English-only model.
    english = next(value.value for value in values if value.language == Language.ENGLISH)
    if english >= values[0].value * 0.9 and english_detector().detect_language_of(text) == Language.ENGLISH:
        return Language.ENGLISH
    if (values[0].value - values[1].value) / values[0].value < 0.10:
        return None
    return values[0].language


def supports_english(question: str) -> bool:
    """Refuse unknown, non-English and selected mixed-language inputs locally."""
    text = unicodedata.normalize("NFKC", question)
    text = "".join(char for char in text if unicodedata.category(char) != "Cf")
    normalized = " ".join(text.lower().split()).strip(".!? ")
    words = WORDS.findall(normalized)
    if set(words) & SWAHILI_MARKERS:
        return False
    if normalized in SHORT_ENGLISH or AGE_ONLY.fullmatch(normalized):
        return True
    if not words:
        return False
    # English can include accented names, but cannot safely contain an
    # unscreened clause in another script.
    if any("LATIN" not in unicodedata.name(char, "") for char in text if char.isalpha()):
        return False
    try:
        detector = language_detector()
        if _language(detector, text) != Language.ENGLISH:
            return False
        # Do not let a long English introduction hide a non-English sentence.
        for clause in re.split(r"[.!?;\n]+", text):
            clause = clause.strip()
            key = " ".join(clause.lower().split())
            if not WORDS.search(clause) or key in SHORT_ENGLISH or AGE_ONLY.fullmatch(key):
                continue
            if _language(detector, clause) != Language.ENGLISH:
                # A confident whole English message can contain a short
                # ambiguous clause (e.g. technical terms). Refuse if English
                # is not also a near-tied interpretation of that clause.
                values = detector.compute_language_confidence_values(clause)
                english = next((value.value for value in values if value.language == Language.ENGLISH), 0)
                if not values or values[0].value <= 0 or english < values[0].value * 0.9:
                    return False
        # Lingua's mixed-language spans are experimental. Ignore short spans
        # (e.g. "a banana"), and require independent agreement on a span of at
        # least three words before treating it as another language.
        for span in detector.detect_multiple_languages_of(text):
            fragment = text[span.start_index:span.end_index]
            if span.language != Language.ENGLISH and len(WORDS.findall(fragment)) >= 3:
                values = detector.compute_language_confidence_values(fragment)
                if _language(detector, fragment) == span.language:
                    # Experimental spans can split fluent English into phrases
                    # resembling another language. Corroborate an ambiguous span
                    # with its full clause, while keeping clear foreign spans blocked.
                    clause = next((part for part in re.finditer(r"[^.!?;\n]+", text)
                                   if part.start() <= span.start_index < part.end()), None)
                    clause_values = detector.compute_language_confidence_values(clause.group()) if clause else []
                    strong_english = (len(clause_values) >= 2
                                      and clause_values[0].language == Language.ENGLISH
                                      and clause_values[0].value >= clause_values[1].value * 2)
                    strong_foreign = len(values) >= 2 and values[0].value >= values[1].value * 2
                    if strong_foreign or not strong_english:
                        return False
        return True
    except Exception:
        # Detector failures must not become permission to generate.
        return False
