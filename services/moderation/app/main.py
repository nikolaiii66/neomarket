from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.db import Base, engine
from app.models import seed_blocking_reasons
from app.db import SessionLocal
from app.routes import router

app = FastAPI(title="NeoMarket Moderation API", version="0.1.0")
app.include_router(router)

Base.metadata.create_all(bind=engine)
with SessionLocal() as session:
    seed_blocking_reasons(session)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"code": "validation_error", "message": str(exc.errors())},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException):
    detail = exc.detail
    if isinstance(detail, dict):
        return JSONResponse(status_code=exc.status_code, content=detail)
    return JSONResponse(status_code=exc.status_code, content={"code": "error", "message": str(detail)})
