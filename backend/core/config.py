# this file loads environment variables from .env and provides backend settings.
# it is imported by backend/core/firebase.py and backend/main.py to read keys, host, and port.
import os
from pathlib import Path
from dotenv import load_dotenv

# find the project root folder.
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
env_path = PROJECT_ROOT / ".env"
load_dotenv(dotenv_path=env_path)


def boolean_setting(name: str, default: str = "false") -> bool:
    value = os.getenv(name, default).strip().lower()
    if value not in {"true", "false"}:
        raise ValueError(f"{name} must be true or false.")
    return value == "true"


class Settings:
    PROJECT_NAME: str = "Parenting Voice Assistant"
    DESCRIPTION: str = "AI-powered voice assistant and coaching system for caregivers."
    VERSION: str = "0.1.0"

    APP_ENV: str = os.getenv("APP_ENV", "development").strip().lower()
    ALLOWED_HOSTS: list[str] = [host.strip() for host in os.getenv("ALLOWED_HOSTS", "").split(",") if host.strip()]
    # An operator confirms the provider account terms; this is not a billing API check.
    GEMINI_PAID_SERVICES_CONFIRMED: bool = boolean_setting("GEMINI_PAID_SERVICES_CONFIRMED")
    FIREBASE_USE_ADC: bool = boolean_setting("FIREBASE_USE_ADC")

    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", 8000))

    STT_MODEL: str = os.getenv("STT_MODEL", "base")

    # read the qdrant connection values loaded from the root .env.
    QDRANT_URL: str | None = os.getenv("QDRANT_URL")
    QDRANT_API_KEY: str | None = os.getenv("QDRANT_API_KEY")
    QDRANT_COLLECTION: str = os.getenv("QDRANT_COLLECTION", "caregiver_guidance_everyday_v4")
    # Provisional cutoff from recorded development examples; not a confidence percentage.
    RETRIEVAL_MIN_SCORE: float = float(os.getenv("RETRIEVAL_MIN_SCORE", "0.50"))
    KENYA_VACCINATION_SCHEDULE_ENABLED: bool = boolean_setting("KENYA_VACCINATION_SCHEDULE_ENABLED", "true")

    COACH_HOURLY_LIMIT: int = int(os.getenv("COACH_HOURLY_LIMIT", "30"))
    COACH_DAILY_LIMIT: int = int(os.getenv("COACH_DAILY_LIMIT", "100"))
    CHILD_CREATE_HOURLY_LIMIT: int = int(os.getenv("CHILD_CREATE_HOURLY_LIMIT", "5"))
    CHILD_CREATE_DAILY_LIMIT: int = int(os.getenv("CHILD_CREATE_DAILY_LIMIT", "20"))

    GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    GEMINI_FALLBACK_MODEL: str = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.8-flash")

    FIREBASE_PROJECT_ID: str | None = os.getenv("FIREBASE_PROJECT_ID")
    AUTH_REQUIRE_MFA: bool = boolean_setting("AUTH_REQUIRE_MFA")

    def validate_deployment(self) -> None:
        if self.APP_ENV not in {"development", "production"}:
            raise ValueError("APP_ENV must be development or production.")
        if self.APP_ENV != "production":
            return
        if not self.ALLOWED_HOSTS or any(
            "*" in host or any(char in host for char in "/:@?# ")
            for host in self.ALLOWED_HOSTS
        ):
            raise ValueError("Production requires explicit host names in ALLOWED_HOSTS, without schemes, ports or wildcards.")
        if not self.GEMINI_PAID_SERVICES_CONFIRMED:
            raise ValueError("Production requires reviewed Gemini paid-service data terms. Unpaid services must not process personal or sensitive information.")

    @property
    def firebase_admin_key_path(self) -> str | None:
        """Resolve the Firebase Admin service account key path.
        Supports both relative paths (relative to project root) and absolute paths.
        """
        raw_path = os.getenv("FIREBASE_ADMIN_KEY_PATH")
        if not raw_path:
            return None
        p = Path(raw_path)
        if not p.is_absolute():
            p = (PROJECT_ROOT / p).resolve()
        return str(p)


settings = Settings()
