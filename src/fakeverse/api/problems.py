"""Errors as RFC 9457 problem details (``application/problem+json``), see docs/problems.md."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from fastapi import Request
from fastapi.responses import JSONResponse

from fakeverse.errors import (
    DataVersionNotFound,
    DataVersionRetired,
    FakeverseError,
    InvalidOption,
    InvalidTemplate,
    LocaleNotSupported,
    PoolExhausted,
    TypeNotSupported,
    UniverseNotFound,
)

MEDIA_TYPE: Final[str] = "application/problem+json"
DOCUMENTATION: Final[str] = "https://github.com/Kentrow/fakeverse/blob/main/docs/problems.md"

STATUS: Final[dict[str, int]] = {
    UniverseNotFound.slug: 404,
    TypeNotSupported.slug: 404,
    DataVersionNotFound.slug: 404,
    DataVersionRetired.slug: 410,
    InvalidOption.slug: 422,
    "count-too-large": 422,
    LocaleNotSupported.slug: 422,
    InvalidTemplate.slug: 422,
    PoolExhausted.slug: 422,
    "payload-too-large": 413,
    "rate-limited": 429,
    "not-found": 404,
    "method-not-allowed": 405,
}

TITLES: Final[dict[str, str]] = {
    "count-too-large": "Count too large",
    "payload-too-large": "Payload too large",
    "rate-limited": "Rate limited",
    "not-found": "Not found",
    "method-not-allowed": "Method not allowed",
}


DOCUMENTATION_URLS: Final[dict[str, str]] = {
    slug: f"{DOCUMENTATION}#{slug}-{status}" for slug, status in STATUS.items()
}
"""URL of the documentation of each problem type (its section in docs/problems.md)."""


class Problem(Exception):
    """An error response of the API."""

    def __init__(
        self,
        slug: str,
        detail: str,
        *,
        title: str | None = None,
        extra: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(detail)
        self.slug = slug
        self.status = STATUS[slug]
        self.title = title or TITLES[slug]
        self.detail = detail
        self.extra = dict(extra or {})
        self.headers = dict(headers or {})

    @classmethod
    def from_error(cls, error: FakeverseError, extra: Mapping[str, Any] | None = None) -> Problem:
        """Convert an engine error, adding the details each kind of error carries."""
        details: dict[str, Any] = dict(extra or {})
        if isinstance(error, InvalidTemplate):
            details["errors"] = error.errors
        if isinstance(error, PoolExhausted):
            details["unique_count"] = error.unique_count
        return cls(error.slug, str(error), title=error.title, extra=details)

    def response(self, request: Request) -> JSONResponse:
        body = {
            "type": f"/problems/{self.slug}",
            "title": self.title,
            "status": self.status,
            "detail": self.detail,
            "instance": request.url.path,
            **self.extra,
        }
        return JSONResponse(body, self.status, headers=self.headers, media_type=MEDIA_TYPE)


def invalid_parameter(errors: list[dict[str, Any]]) -> Problem:
    """An ``invalid-parameter`` problem listing every faulty parameter."""
    names = ", ".join(str(error["name"]) for error in errors)
    return Problem(
        InvalidOption.slug,
        f"Invalid parameter(s): {names}.",
        title=InvalidOption.title,
        extra={"errors": errors},
    )
