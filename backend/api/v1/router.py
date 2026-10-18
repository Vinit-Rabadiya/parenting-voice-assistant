# this file groups all v1 api routes (health, auth, etc.) into one central router.
# it is imported by backend/main.py and plugged into the fastapi application.
from fastapi import APIRouter
from backend.api.v1.endpoints import auth, children, coaching, health, speech

api_router = APIRouter()
api_router.include_router(health.router, tags=["Health"])
api_router.include_router(auth.router, tags=["Auth"])
api_router.include_router(speech.router, tags=["Speech"])
api_router.include_router(children.router, tags=["Children"])
api_router.include_router(coaching.router, tags=["Coaching"])
