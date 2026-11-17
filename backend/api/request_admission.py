"""Hold processing admission through completion, including streamed responses."""

from fastapi import Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from backend.core.request_admission import AdmissionRejected
from backend.core.security import require_authenticated_user


async def require_processing_slot(request: Request, user=Depends(require_authenticated_user)):
    admission = getattr(request.app.state, "request_admission", None)
    if admission is None:
        raise HTTPException(status_code=503, detail="Service is starting. Please try again shortly.")
    try:
        with admission.processing(user["uid"]):
            yield
    except AdmissionRejected as exc:
        raise HTTPException(status_code=429, detail=str(exc), headers={"Retry-After": "3"}) from None


async def run_processing_worker(request, uid, operation, *args, speech=False, **kwargs):
    admission = request.app.state.request_admission

    def work():
        with admission.worker(uid, speech=speech):
            return operation(*args, **kwargs)

    try:
        return await run_in_threadpool(work)
    except AdmissionRejected as exc:
        raise HTTPException(status_code=429, detail=str(exc), headers={"Retry-After": "3"}) from None

