"""Prometheus metrics of the API, when enabled."""

from __future__ import annotations

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    Info,
    disable_created_metrics,
    generate_latest,
)

from fakeverse import __version__
from fakeverse.engine.revision import ENGINE_REVISION


class Metrics:
    """The metrics of one application, in their own registry."""

    content_type = CONTENT_TYPE_LATEST

    def __init__(self, default_data_version: str) -> None:
        disable_created_metrics()  # type: ignore[no-untyped-call]
        self.registry = CollectorRegistry()
        self.requests = Counter(
            "fakeverse_http_requests",
            "HTTP requests.",
            ["route", "status"],
            registry=self.registry,
        )
        self.duration = Histogram(
            "fakeverse_http_request_duration_seconds",
            "Duration of HTTP requests.",
            ["route"],
            registry=self.registry,
        )
        self.generated = Counter(
            "fakeverse_generated_items",
            "Generated items.",
            ["universe", "type"],
            registry=self.registry,
        )
        self.rate_limited = Counter(
            "fakeverse_rate_limited", "Requests rejected by the rate limit.", registry=self.registry
        )
        info = Info("fakeverse", "Versions of the service.", registry=self.registry)
        info.info(
            {
                "package_version": __version__,
                "engine_revision": str(ENGINE_REVISION),
                "data_version": default_data_version,
            }
        )

    def render(self) -> bytes:
        return generate_latest(self.registry)
