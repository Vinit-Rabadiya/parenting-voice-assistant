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

    key_path = settings.firebase_admin_key_path
    if not key_path:
        raise RuntimeError("FIREBASE_ADMIN_KEY_PATH is required.")

    # make sure we connect to live firebase, not a local fake.
    if os.getenv("FIREBASE_AUTH_EMULATOR_HOST"):
        raise RuntimeError("This backend expects live Firebase Authentication.")

    # load the private key file.
    credential = credentials.Certificate(key_path)

    # make sure the key matches the project we want to use.
    if credential.project_id != settings.FIREBASE_PROJECT_ID:
        raise RuntimeError("Firebase credential and project ID do not match.")

    # connect to firebase for backend operations.
    return firebase_admin.initialize_app(
        credential,
        options={
            "projectId": settings.FIREBASE_PROJECT_ID,
            "httpTimeout": 5,
        },
    )
