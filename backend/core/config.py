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
    VERSION: str = "0.2.0"

    APP_ENV: str = os.getenv("APP_ENV", "development").strip().lower()
    SERVE_FRONTEND: bool = boolean_setting("SERVE_FRONTEND")
    ALLOWED_HOSTS: list[str] = [host.strip() for host in os.getenv("ALLOWED_HOSTS", "").split(",") if host.strip()]
    # Custom Firebase browser auth domains; default project domains are derived automatically.
    CSP_AUTH_ORIGINS: list[str] = [origin.strip() for origin in os.getenv("CSP_AUTH_ORIGINS", "").split(",") if origin.strip()]
    # An operator confirms the provider account terms; this is not a billing API check.
    GEMINI_PAID_SERVICES_CONFIRMED: bool = boolean_setting("GEMINI_PAID_SERVICES_CONFIRMED")
    # An operator confirms that free-tier model requests contain only non-personal test material.
    # This setting neither anonymizes input nor checks or enables billing.
    GEMINI_NONPERSONAL_TESTING_CONFIRMED: bool = boolean_setting("GEMINI_NONPERSONAL_TESTING_CONFIRMED")
    FIREBASE_USE_ADC: bool = boolean_setting("FIREBASE_USE_ADC")

    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", 8000))

    STT_MODEL: str = os.getenv("STT_MODEL", "base")

    # read the qdrant connection values loaded from the root .env.
    QDRANT_URL: str | None = os.getenv("QDRANT_URL")
    QDRANT_API_KEY: str | None = os.getenv("QDRANT_API_KEY")
    QDRANT_COLLECTION: str = os.getenv("QDRANT_COLLECTION", "caregiver_guidance_everyday_v4")
    QDRANT_CORPUS_REVISION: str = os.getenv("QDRANT_CORPUS_REVISION", "")
    RETRIEVAL_CACHE_TTL_SECONDS: float = float(os.getenv("RETRIEVAL_CACHE_TTL_SECONDS", "60"))
    QDRANT_WARMUP_ENABLED: bool = boolean_setting("QDRANT_WARMUP_ENABLED", "false")
    QDRANT_WARMUP_TIMEOUT_SECONDS: float = float(os.getenv("QDRANT_WARMUP_TIMEOUT_SECONDS", "5.0"))
    QDRANT_WARMUP_RETRIES: int = int(os.getenv("QDRANT_WARMUP_RETRIES", "2"))
    # Provisional cutoff from recorded development examples; not a confidence percentage.
    RETRIEVAL_MIN_SCORE: float = float(os.getenv("RETRIEVAL_MIN_SCORE", "0.50"))
    KENYA_VACCINATION_SCHEDULE_ENABLED: bool = boolean_setting("KENYA_VACCINATION_SCHEDULE_ENABLED", "true")


    GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    GEMINI_FALLBACK_MODEL: str = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.8-flash")
    COACHING_PROVIDER: str = os.getenv("COACHING_PROVIDER", "gemini").strip().lower()
    COACHING_PROVIDER_FAILOVER: bool = boolean_setting("COACHING_PROVIDER_FAILOVER")
    COACHING_PROVIDER_COOLDOWN_SECONDS: int = int(os.getenv("COACHING_PROVIDER_COOLDOWN_SECONDS", "60"))
    GROQ_API_KEY: str | None = os.getenv("GROQ_API_KEY")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")
    GROQ_FALLBACK_MODEL: str = os.getenv("GROQ_FALLBACK_MODEL", "")
    GROQ_DATA_TERMS_CONFIRMED: bool = boolean_setting("GROQ_DATA_TERMS_CONFIRMED")
    GROQ_NONPERSONAL_TESTING_CONFIRMED: bool = boolean_setting("GROQ_NONPERSONAL_TESTING_CONFIRMED")

    @property
    def coaching_model(self):
        return self.GROQ_MODEL if self.COACHING_PROVIDER == "groq" else self.GEMINI_MODEL

    @property
    def coaching_fallback_model(self):
        return self.GROQ_FALLBACK_MODEL if self.COACHING_PROVIDER == "groq" else self.GEMINI_FALLBACK_MODEL

    @property
    def provider_data_allowed(self):
        return all(self.data_allowed_for(provider) for provider in self.coaching_providers)

    @property
    def coaching_providers(self):
        if not self.COACHING_PROVIDER_FAILOVER:
            return (self.COACHING_PROVIDER,)
        return (self.COACHING_PROVIDER, "gemini" if self.COACHING_PROVIDER == "groq" else "groq")

    def data_allowed_for(self, provider: str) -> bool:
        if provider == "groq":
            return self.GROQ_DATA_TERMS_CONFIRMED is True or self.GROQ_NONPERSONAL_TESTING_CONFIRMED is True
        if provider == "gemini":
            return self.GEMINI_PAID_SERVICES_CONFIRMED is True or self.GEMINI_NONPERSONAL_TESTING_CONFIRMED is True
        return False

    FIREBASE_PROJECT_ID: str | None = os.getenv("FIREBASE_PROJECT_ID")
    AUTH_REQUIRE_MFA: bool = boolean_setting("AUTH_REQUIRE_MFA")
    AUTH_SESSION_CACHE_TTL_SECONDS: int = int(os.getenv("AUTH_SESSION_CACHE_TTL_SECONDS", "60"))

    def validate_deployment(self) -> None:
        if type(self.AUTH_SESSION_CACHE_TTL_SECONDS) is not int or not 0 <= self.AUTH_SESSION_CACHE_TTL_SECONDS <= 18000:
            raise ValueError("AUTH_SESSION_CACHE_TTL_SECONDS must be an integer between 0 and 18000.")
        if self.APP_ENV not in {"development", "production"}:
            raise ValueError("APP_ENV must be development or production.")
        if self.APP_ENV != "production":
            return
        if not self.ALLOWED_HOSTS or any(
            "*" in host or any(char in host for char in "/:@?# ")
            for host in self.ALLOWED_HOSTS
        ):
            raise ValueError("Production requires explicit host names in ALLOWED_HOSTS, without schemes, ports or wildcards.")
        if not self.data_allowed_for(self.COACHING_PROVIDER):
            raise ValueError("Production requires confirmed data terms for the selected provider or confirmed non-personal testing.")
        if not self.provider_data_allowed:
            raise ValueError("Production requires confirmed data terms for every failover provider or confirmed non-personal testing.")

    def validate_coaching(self) -> None:
        """Check local generation settings without contacting the provider."""
        if (type(self.QDRANT_WARMUP_TIMEOUT_SECONDS) not in (int, float)
                or not 0 < self.QDRANT_WARMUP_TIMEOUT_SECONDS <= 30):
            raise ValueError("QDRANT_WARMUP_TIMEOUT_SECONDS must be greater than zero and at most 30.")
        if type(self.QDRANT_WARMUP_RETRIES) is not int or not 0 <= self.QDRANT_WARMUP_RETRIES <= 3:
            raise ValueError("QDRANT_WARMUP_RETRIES must be an integer from zero to three.")
        if self.COACHING_PROVIDER not in {"gemini", "groq"}:
            raise ValueError("COACHING_PROVIDER must be gemini or groq.")
        if (type(self.COACHING_PROVIDER_COOLDOWN_SECONDS) is not int
                or not 1 <= self.COACHING_PROVIDER_COOLDOWN_SECONDS <= 86400):
            raise ValueError("COACHING_PROVIDER_COOLDOWN_SECONDS must be an integer from 1 to 86400.")
        for provider in self.coaching_providers:
            prefix = provider.upper()
            for name in (f"{prefix}_API_KEY", f"{prefix}_MODEL"):
                value = getattr(self, name)
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"{name} must be configured before starting the backend.")
            fallback = getattr(self, f"{prefix}_FALLBACK_MODEL")
            if not isinstance(fallback, str):
                raise ValueError(f"{prefix}_FALLBACK_MODEL must be a model name or an empty string.")
            if provider == "groq":
                from backend.services.groq_client import GROQ_MODELS
                if self.GROQ_MODEL not in GROQ_MODELS or (fallback and fallback not in GROQ_MODELS):
                    raise ValueError("Choose a supported Groq model.")

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
