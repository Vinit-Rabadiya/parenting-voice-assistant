import os

import firebase_admin
from firebase_admin import credentials

from backend.config import settings


def initialize_firebase() -> firebase_admin.App:
    # stop server startup if the required firebase settings are missing.
    if not settings.FIREBASE_PROJECT_ID:
        raise RuntimeError("FIREBASE_PROJECT_ID is required.")

    if not settings.FIREBASE_ADMIN_KEY_PATH:
        raise RuntimeError("FIREBASE_ADMIN_KEY_PATH is required.")

    # use the real firebase project, not the local test version.
    if os.getenv("FIREBASE_AUTH_EMULATOR_HOST"):
        raise RuntimeError("This backend expects live Firebase Authentication.")

    # load the private key file on the server only.
    credential = credentials.Certificate(settings.FIREBASE_ADMIN_KEY_PATH)

    # make sure the key belongs to the project we intend to use.
    if credential.project_id != settings.FIREBASE_PROJECT_ID:
        raise RuntimeError("Firebase credential and project ID do not match.")

    # prepare firebase for backend use; user login checks happen separately.
    return firebase_admin.initialize_app(
        credential,
        options={
            "projectId": settings.FIREBASE_PROJECT_ID,
            "httpTimeout": 5,
        },
    )
