"""HTTP responses of generations: format negotiation and common headers."""

from __future__ import annotations

from fastapi import Response

from fakeverse.fakeverse import GenerationResult
from fakeverse.formats import MEDIA_TYPES, OutputFormat, render

_ACCEPT: dict[str, OutputFormat] = {
    "application/x-ndjson": OutputFormat.NDJSON,
    "text/csv": OutputFormat.CSV,
    "application/json": OutputFormat.JSON,
}


def negotiate(requested: OutputFormat | None, accept: str | None) -> OutputFormat:
    """The ``format`` parameter wins; otherwise the first known type of ``Accept``; JSON."""
    if requested is not None:
        return requested
    for part in (accept or "").split(","):
        media_type = part.split(";")[0].strip().lower()
        if media_type in _ACCEPT:
            return _ACCEPT[media_type]
    return OutputFormat.JSON


def generation_headers(result: GenerationResult) -> dict[str, str]:
    """Headers sent with every format."""
    meta = result.meta
    return {
        "Fakeverse-Seed": str(meta.seed),
        "Fakeverse-Data-Version": meta.data_version,
        "Fakeverse-Engine-Revision": str(meta.engine_revision),
        "Fakeverse-Locale": meta.locale,
        "Fakeverse-Locale-Fallbacks": str(meta.locale_fallbacks),
        "Fakeverse-Duplicates": str(meta.duplicates),
    }


def generation_response(
    result: GenerationResult,
    output: OutputFormat,
    *,
    explain: bool,
    headers: dict[str, str],
) -> Response:
    """Render a generation in ``output`` with the common headers."""
    body = render(result, output, explain=explain)
    return Response(
        body.encode(),
        media_type=MEDIA_TYPES[output],
        headers={**generation_headers(result), **headers},
    )
