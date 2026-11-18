from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.db import Base, engine
from app.routes import router

app = FastAPI(title="NeoMarket B2B API", version="0.1.0")
app.include_router(router)

Base.metadata.create_all(bind=engine)


def _field_names(errors: list[dict]) -> set[str]:
    names: set[str] = set()
    for err in errors:
        loc = err.get("loc") or ()
        for part in loc:
            if part not in {"body", "query", "path", "header"}:
                names.add(str(part))
    return names


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    fields = _field_names(errors)
    # Canon/DoD for US-B2B-01: product create field issues → 400 INVALID_REQUEST.
    if request.url.path.rstrip("/").endswith("/api/v1/products") and request.method == "POST":
        if fields & {"category_id", "images", "title", "description"}:
            if "category_id" in fields:
                message = "category_id must be a valid UUID"
            elif "images" in fields:
                message = "At least one image is required"
            else:
                message = "Invalid request"
            return JSONResponse(
                status_code=400,
                content={"code": "INVALID_REQUEST", "message": message},
            )
    return JSONResponse(
        status_code=422,
        content={"code": "validation_error", "message": str(errors)},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException):
    detail = exc.detail
    if isinstance(detail, dict):
        return JSONResponse(status_code=exc.status_code, content=detail)
    return JSONResponse(status_code=exc.status_code, content={"code": "error", "message": str(detail)})
