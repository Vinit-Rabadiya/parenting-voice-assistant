import os

import firebase_admin
from firebase_admin import credentials

from backend.config import settings


def initialize_firebase() -> firebase_admin.App:
    if not settings.FIREBASE_PROJECT_ID:
        raise RuntimeError("FIREBASE_PROJECT_ID is required.")

    if not settings.FIREBASE_ADMIN_KEY_PATH:
        raise RuntimeError("FIREBASE_ADMIN_KEY_PATH is required.")

    if os.getenv("FIREBASE_AUTH_EMULATOR_HOST"):
        raise RuntimeError("This backend expects live Firebase Authentication.")

    credential = credentials.Certificate(settings.FIREBASE_ADMIN_KEY_PATH)

    if credential.project_id != settings.FIREBASE_PROJECT_ID:
        raise RuntimeError("Firebase credential and project ID do not match.")

    return firebase_admin.initialize_app(
        credential,
        options={
            "projectId": settings.FIREBASE_PROJECT_ID,
            "httpTimeout": 5,
        },
    )