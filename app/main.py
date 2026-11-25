"""FastAPI 앱 팩토리. 테스트는 create_app(Settings(...))으로 격리한다."""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

from app.api import pages, routes
from app.api.pages import setup_filters
from app.config import Settings
from app.db import Database
from app.errors import AppError
from app.services.review import ReviewService
from app.services.vendors import VendorRegistry
from app.version import APP_NAME, APP_VERSION

logger = logging.getLogger(__name__)

CSP = (
    "default-src 'none'; "
    "style-src 'self'; "
    "img-src 'self' data:; "
    "form-action 'self'; "
    "base-uri 'none'; "
    "frame-ancestors 'none'"
)


class _BodyTooLarge(Exception):
    pass


class BodySizeLimitMiddleware:
    """Content-Length와 스트림 바이트를 모두 검사한다."""

    def __init__(self, app, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or scope.get("method") not in {"POST", "PUT", "PATCH"}:
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        raw_length = headers.get(b"content-length")
        if raw_length:
            try:
                length = int(raw_length)
            except ValueError:
                length = 0
            if length > self.max_bytes:
                await self._reject(send)
                return

        total = 0
        started = False

        async def wrapped_send(message):
            nonlocal started
            if message.get("type") == "http.response.start":
                started = True
            await send(message)

        async def limited_receive():
            nonlocal total
            message = await receive()
            if message.get("type") == "http.request":
                total += len(message.get("body", b""))
                if total > self.max_bytes:
                    raise _BodyTooLarge
            return message

        try:
            await self.app(scope, limited_receive, wrapped_send)
        except _BodyTooLarge:
            if not started:
                await self._reject(send)

    async def _reject(self, send) -> None:
        body = json.dumps(
            {
                "error": {
                    "code": "E_BODY_TOO_LARGE",
                    "message": f"요청 본문은 {self.max_bytes}바이트 이하여야 합니다.",
                }
            },
            ensure_ascii=False,
        ).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, limit_per_minute: int, trust_proxy_headers: bool = False) -> None:
        super().__init__(app)
        self.limit = limit_per_minute
        self.trust_proxy_headers = trust_proxy_headers
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _client_key(self, request: Request) -> str:
        if self.trust_proxy_headers:
            forwarded = request.headers.get("x-forwarded-for")
            if forwarded:
                return next((hop.strip() for hop in forwarded.split(",") if hop.strip()), "unknown")
        return request.client.host if request.client else "unknown"

    async def dispatch(self, request: Request, call_next):
        if self.limit <= 0 or not request.url.path.startswith("/api"):
            return await call_next(request)
        client = self._client_key(request)
        now = time.monotonic()
        with self._lock:
            bucket = self._hits[client]
            while bucket and bucket[0] < now - 60:
                bucket.popleft()
            if len(bucket) >= self.limit:
                retry_after = max(1, int(60 - (now - bucket[0])))
                return JSONResponse(
                    status_code=429,
                    headers={"Retry-After": str(retry_after)},
                    content={
                        "error": {
                            "code": "E_RATE_LIMITED",
                            "message": "요청이 너무 많습니다. 잠시 후 다시 시도해주세요.",
                            "retry_after_seconds": retry_after,
                        }
                    },
                )
            bucket.append(now)
            if len(self._hits) > 10_000:
                for key in [key for key, value in self._hits.items() if not value]:
                    self._hits.pop(key, None)
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("Content-Security-Policy", CSP)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        response.headers.setdefault("X-Robots-Tag", "noindex, nofollow")
        if request.url.path.startswith(("/api", "/documents")):
            response.headers.setdefault("Cache-Control", "no-store")
        return response


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    settings.ensure_dirs()
    db = Database(settings.db_path)
    db.initialize()
    registry = VendorRegistry.load(settings.vendor_registry_path)
    service = ReviewService(settings, registry, db)

    templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
    setup_filters(templates)

    app = FastAPI(
        title=APP_NAME,
        version=APP_VERSION,
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.state.settings = settings
    app.state.db = db
    app.state.registry = registry
    app.state.service = service
    app.state.templates = templates

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_upload_bytes)
    app.add_middleware(
        RateLimitMiddleware,
        limit_per_minute=settings.rate_limit_per_minute,
        trust_proxy_headers=settings.trust_proxy_headers,
    )

    app.include_router(routes.router)
    app.include_router(pages.router)
    app.mount(
        "/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static"
    )

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        return JSONResponse(status_code=exc.status_code, content=exc.to_body())

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "E_VALIDATION",
                    "message": "요청 형식이 올바르지 않습니다.",
                    "details": [
                        {"loc": list(error.get("loc", [])), "msg": error.get("msg", "")}
                        for error in exc.errors()
                    ],
                }
            },
        )

    @app.exception_handler(Exception)
    async def internal_error_handler(request: Request, exc: Exception):
        logger.exception("unhandled error path=%s", request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "E_INTERNAL",
                    "message": "서버 내부 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
                }
            },
        )

    logger.info("app ready version=%s db=%s", APP_VERSION, settings.db_path)
    return app
