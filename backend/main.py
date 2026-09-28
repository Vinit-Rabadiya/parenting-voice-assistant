# this file starts the backend server, connects to firebase, and mounts all api routes.
# it is run by uvicorn (python -m uvicorn backend.main:app) and used by tests in tests/conftest.py.
from contextlib import asynccontextmanager
import firebase_admin
from fastapi import FastAPI
from backend.core.config import settings
from backend.core.firebase import initialize_firebase
from backend.api.v1.router import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # connect to firebase when the server starts.
    app.state.firebase = initialize_firebase()
    try:
        yield
    finally:
        # close the local firebase connection when the server stops.
        if hasattr(app.state, "firebase") and app.state.firebase:
            firebase_admin.delete_app(app.state.firebase)


app = FastAPI(
    title=settings.PROJECT_NAME,
    description=settings.DESCRIPTION,
    version=settings.VERSION,
    lifespan=lifespan,
)

# connect the api routes to the main app.
app.include_router(api_router)

# also allow accessing the routes under /api/v1.
app.include_router(api_router, prefix="/api/v1")
