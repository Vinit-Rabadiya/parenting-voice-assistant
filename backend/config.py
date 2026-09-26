import os
from pathlib import Path
from dotenv import load_dotenv


env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)


class Settings:
    PROJECT_NAME: str = "Parenting Voice Assistant"
    DESCRIPTION: str = "AI-powered voice assistant and coaching system for caregivers."
    VERSION: str = "1.0.0"

    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", 8000))

    GROQ_API_KEY: str | None = os.getenv("GROQ_API_KEY")
    FIREBASE_PROJECT_ID: str | None = os.getenv("FIREBASE_PROJECT_ID")
    FIREBASE_ADMIN_KEY_PATH: str | None = os.getenv("FIREBASE_ADMIN_KEY_PATH")
    GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY")

    DB_PATH: Path = Path(__file__).resolve().parent.parent / "mamacare.db"


settings = Settings()
