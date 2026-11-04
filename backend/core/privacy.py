"""Versioned processing notice; change the version when its terms change."""

from backend.core.config import settings


def generation_notice(provider: str, failover: bool = False) -> tuple[str, str]:
    if failover and provider in {"groq", "gemini"}:
        return "2026-11-04.dual.1", "Groq and Gemini (Google), the AI services"
    if provider == "groq":
        return "2026-11-03.groq.1", "Groq, the AI service"
    if provider == "gemini":
        return "2026-11-01.1", "Gemini, Google's AI service"
    raise ValueError("Unsupported coaching provider.")


CONSENT_VERSION, GENERATION_PROVIDER = generation_notice(settings.COACHING_PROVIDER, settings.COACHING_PROVIDER_FAILOVER)
# Feedback-sharing terms are unchanged; earlier explicit permission remains valid.
FEEDBACK_CONSENT_VERSIONS = frozenset({"2026-10-26.2", "2026-11-01.1", "2026-11-03.groq.1", "2026-11-04.dual.1"})
PRIVACY_NOTICE = [
    "Your child's name, date of birth, and optional milestones are stored in their profile. Their age and saved milestones are used to provide guidance suited to their stage of development. Milestones are caregiver observations, not a medical assessment.",
    "Optional health and care notes, including allergies, diagnosed conditions, history, care instructions and test-result notes, are stored privately with the child profile. You can edit or clear them. These notes are not shown in the administrator dashboard. Health notes are used in replies only when you enable that choice and it is available. These notes are not verified clinical records and the service does not diagnose conditions or interpret medical tests.",
    "Your messages, selected activities, and recent chat messages are used to provide relevant caregiving guidance.",
    "Qdrant Cloud, a service outside this app, receives your question and sometimes an earlier message to find relevant guidance.",
    f"{GENERATION_PROVIDER}, {'can receive' if settings.COACHING_PROVIDER_FAILOVER else 'receives'} your question, your child's age, saved milestones, the activity you selected, reference information, and a limited number of recent chat messages to create the reply. If you enable health notes for replies and the feature is available, those notes are also shared. Profile names and dates of birth are not automatically included. Health notes are not sent to Qdrant Cloud."
    + (" The app automatically tries the other AI service when one reaches its request limit; the same message and permitted context may be sent to both services for that reply." if settings.COACHING_PROVIDER_FAILOVER else ""),
    "Your chats, the information used for replies, dates and times, and optional feedback are saved in your account so you can refer to them later.",
    "Optional ratings and feedback reasons submitted after accepting this notice are used for service-quality statistics. Administrators see counts for each rating and reason, including when there is only one response.",
    "Optional written feedback comments submitted after accepting this notice can be read by administrators, together with the rating and selected reasons, to review problems and improve the service. Your chats, transcripts, account identity and child profile are not attached. Do not include names or other private details in a comment. Earlier feedback is not shared automatically, and feedback is not used to train models automatically.",
    "Voice recordings are used to turn speech into written words. The app does not deliberately save the recordings. The words you send are saved in your chat.",
    "Your chats and feedback stay until you delete the chat, its child profile, or your account. Separate services may keep shared information for different lengths of time. Backup copies may not be removed immediately.",
    "You do not have to agree. You can still open account settings and view or delete existing profiles and chats. You must agree before adding or changing profiles, recording your voice, requesting guidance, or sending feedback. Avoid sharing private details that are not needed for your question.",
]
