from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.config import settings

MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
ALLOWED_FETCH_SITES = {"same-origin", "none"}


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method.upper() not in MUTATING_METHODS:
            return await call_next(request)

        fetch_site = request.headers.get("sec-fetch-site")
        if fetch_site is not None and fetch_site.lower() not in ALLOWED_FETCH_SITES:
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF check failed"},
            )

        origin = request.headers.get("origin")
        if origin is not None:
            allowed = set(settings.csrf_allowed_origins)
            request_origin = f"{request.url.scheme}://{request.headers.get('host')}"
            if origin not in allowed and origin != request_origin:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "CSRF check failed"},
                )

        return await call_next(request)
