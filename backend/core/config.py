# this file loads environment variables from .env and provides backend settings.
# it is imported by backend/core/firebase.py and backend/main.py to read keys, host, and port.
import os
from pathlib import Path
from dotenv import load_dotenv

# find the project root folder.
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
env_path = PROJECT_ROOT / ".env"
load_dotenv(dotenv_path=env_path)


class Settings:
    PROJECT_NAME: str = "Parenting Voice Assistant"
    DESCRIPTION: str = "AI-powered voice assistant and coaching system for caregivers."
    VERSION: str = "1.0.0"

    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", 8000))

    FIREBASE_PROJECT_ID: str | None = os.getenv("FIREBASE_PROJECT_ID")
    GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY")

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
