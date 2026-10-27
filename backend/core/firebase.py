# this file initializes the firebase admin sdk on the server using private key credentials.
# it is called in backend/main.py when the server starts up to enable token checking.
import os
import firebase_admin
from firebase_admin import credentials
from backend.core.config import settings


def initialize_firebase() -> firebase_admin.App:
    # check that the required settings are provided.
    if not settings.FIREBASE_PROJECT_ID:
        raise RuntimeError("FIREBASE_PROJECT_ID is required.")

    # Connect to Firebase rather than a local emulator.
    if os.getenv("FIREBASE_AUTH_EMULATOR_HOST") or os.getenv("FIRESTORE_EMULATOR_HOST"):
        raise RuntimeError("This backend expects live Firebase Authentication and Firestore.")

    key_path = settings.firebase_admin_key_path
    if settings.FIREBASE_USE_ADC:
        if key_path:
            raise RuntimeError("Unset FIREBASE_ADMIN_KEY_PATH when FIREBASE_USE_ADC is true.")
        # Google-managed hosting can use an attached service account instead of
        # distributing a long-lived private key file with the application.
        credential = credentials.ApplicationDefault()
    else:
        if not key_path:
            raise RuntimeError("FIREBASE_ADMIN_KEY_PATH is required unless FIREBASE_USE_ADC is true.")
        credential = credentials.Certificate(key_path)

    # Verify that the key matches the configured project.
    if credential.project_id and credential.project_id != settings.FIREBASE_PROJECT_ID:
        raise RuntimeError("Firebase credential and project ID do not match.")

    # connect to firebase for backend operations.
    return firebase_admin.initialize_app(
        credential,
        options={
            "projectId": settings.FIREBASE_PROJECT_ID,
            "httpTimeout": 5,
        },
    )
