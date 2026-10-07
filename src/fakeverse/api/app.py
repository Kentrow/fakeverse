"""FastAPI application of Fakeverse.

Run with ``uvicorn fakeverse.api.app:app``. Tests and embedders use :func:`create_app`.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from collections.abc import Awaitable, Callable
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import RedirectResponse
from starlette.exceptions import HTTPException

from fakeverse import __version__
from fakeverse.api.metrics import Metrics
from fakeverse.api.problems import MEDIA_TYPE as PROBLEM_MEDIA_TYPE
from fakeverse.api.problems import STATUS, Problem, documentation_url, invalid_parameter
from fakeverse.api.ratelimit import Clock, RateLimiter, client_ip, rate_key, truncate_ip
from fakeverse.api.routes import AppState, router
from fakeverse.api.schemas import DOCUMENTED_MODELS
from fakeverse.api.settings import Settings
from fakeverse.api.snapshots import SnapshotStore
from fakeverse.errors import FakeverseError

EXEMPT_PATHS = frozenset({"/v1/health", "/metrics"})
EXPOSED_HEADERS = [
    "Fakeverse-Seed",
    "Fakeverse-Data-Version",
    "Fakeverse-Engine-Revision",
    "Fakeverse-Locale",
    "Fakeverse-Locale-Fallbacks",
    "Fakeverse-Duplicates",
    "RateLimit-Limit",
    "RateLimit-Remaining",
    "RateLimit-Reset",
    "Retry-After",
    "ETag",
]

logger = logging.getLogger("fakeverse.api")


class _StdoutHandler(logging.StreamHandler[Any]):
    """Writes to the current ``sys.stdout``, even when it is replaced after start-up."""

    @property
    def stream(self) -> Any:
        return sys.stdout

    @stream.setter
    def stream(self, _value: Any) -> None:
        pass


def _configure_logging(level: str) -> None:
    if not any(isinstance(handler, _StdoutHandler) for handler in logger.handlers):
        handler = _StdoutHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.propagate = False
    logger.setLevel(level.upper())


def create_app(settings: Settings | None = None, *, clock: Clock | None = None) -> FastAPI:
    """Build the application.

    Args:
        settings: configuration; read from the environment when omitted.
        clock: monotonic clock of the rate limiter, injectable for tests.
    """
    settings = settings if settings is not None else Settings()
    _configure_logging(settings.log_level)
    store = SnapshotStore.load(settings.data_dir, settings.disabled)
    limiter = None
    if settings.rate_per_second > 0:
        limiter = RateLimiter(
            settings.rate_per_second, settings.rate_burst, clock or time.monotonic
        )
    metrics = Metrics(store.default_version) if settings.metrics_enabled else None
    state = AppState(settings=settings, store=store, limiter=limiter, metrics=metrics)

    app = FastAPI(
        title="Fakeverse API",
        version=__version__,
        description="Coherent fake data themed by fictional universes.",
    )
    app.state.fakeverse = state
    app.include_router(router)

    @app.get("/problems/{slug}", include_in_schema=False)
    def problem_type(slug: str) -> RedirectResponse:
        """The ``type`` of a problem is ``/problems/<slug>``: it leads to its documentation."""
        if slug not in STATUS:
            raise Problem("not-found", f"Unknown problem type '{slug}'.")
        return RedirectResponse(documentation_url(slug), status_code=302)

    _add_error_handlers(app)
    _add_observability(app, state)
    # Added last, hence outermost: CORS headers also reach the 429 responses of the rate limit.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
        expose_headers=EXPOSED_HEADERS,
    )
    _document_models(app)
    if metrics is not None:

        @app.get("/metrics", include_in_schema=False)
        def metrics_endpoint() -> Response:
            return Response(metrics.render(), media_type=metrics.content_type)

    return app


def _document_models(app: FastAPI) -> None:
    """Register the models that hand-written OpenAPI responses reference, and describe
    validation errors as the problems they really are."""

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is None:
            schema = get_openapi(
                title=app.title,
                version=app.version,
                description=app.description,
                routes=app.routes,
            )
            components = schema.setdefault("components", {}).setdefault("schemas", {})
            for model in DOCUMENTED_MODELS:
                definition = model.model_json_schema(ref_template="#/components/schemas/{model}")
                components.update(definition.pop("$defs", {}))
                components[str(definition["title"])] = definition
            for name in ("HTTPValidationError", "ValidationError"):
                components.pop(name, None)
            problem = {"$ref": "#/components/schemas/Problem"}
            for operations in schema["paths"].values():
                for operation in operations.values():
                    invalid = operation.get("responses", {}).get("422")
                    if invalid is not None:
                        invalid["content"] = {PROBLEM_MEDIA_TYPE: {"schema": problem}}
            app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = openapi  # type: ignore[method-assign]


def _add_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(Problem)
    async def problem_handler(request: Request, problem: Problem) -> Response:
        return problem.response(request)

    @app.exception_handler(FakeverseError)
    async def error_handler(request: Request, error: FakeverseError) -> Response:
        return Problem.from_error(error).response(request)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, error: RequestValidationError) -> Response:
        errors = [
            {
                "name": str(e["loc"][-1]) if e["loc"] else "request",
                "location": str(e["loc"][0]) if e["loc"] else "request",
                "message": e["msg"],
            }
            for e in error.errors()
        ]
        return invalid_parameter(errors).response(request)

    @app.exception_handler(HTTPException)
    async def http_handler(request: Request, error: HTTPException) -> Response:
        slug = (
            "method-not-allowed"
            if error.status_code == HTTPStatus.METHOD_NOT_ALLOWED
            else "not-found"
        )
        return Problem(slug, str(error.detail)).response(request)


def _add_observability(app: FastAPI, state: AppState) -> None:
    @app.middleware("http")
    async def observe(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        start = time.perf_counter()
        peer = request.client.host if request.client else None
        # Every X-Forwarded-For line counts: a proxy may append its own line after the client's.
        forwarded = ", ".join(request.headers.getlist("x-forwarded-for")) or None
        ip = client_ip(peer, forwarded, state.settings.proxy_networks)
        decision = None
        limited = request.method != "OPTIONS" and request.url.path not in EXEMPT_PATHS
        if state.limiter is not None and limited:
            decision = state.limiter.check(rate_key(ip))
        if decision is not None and not decision.allowed:
            if state.metrics is not None:
                state.metrics.rate_limited.inc()
            problem = Problem(
                "rate-limited",
                f"Too many requests; retry in {decision.retry_after} s.",
                extra={"retry_after": decision.retry_after},
                headers=decision.headers(),
            )
            response: Response = problem.response(request)
        else:
            response = await call_next(request)
            if decision is not None:
                response.headers.update(decision.headers())
        duration = time.perf_counter() - start
        route = request.scope.get("route")
        route_path = getattr(route, "path", "unmatched")
        if state.metrics is not None:
            state.metrics.requests.labels(route_path, str(response.status_code)).inc()
            state.metrics.duration.labels(route_path).observe(duration)
        entry: dict[str, Any] = {
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": round(duration * 1000, 3),
            "universe": None,
            "type": None,
            "count": None,
            "format": None,
            **getattr(request.state, "log", {}),
            "client_ip": truncate_ip(ip),
        }
        logger.info(json.dumps(entry, ensure_ascii=False))
        return response


app = create_app()
