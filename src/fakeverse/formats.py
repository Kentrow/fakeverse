"""Output formats of a generation: JSON, NDJSON and CSV.

Shared by the CLI and the HTTP API.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Mapping
from enum import StrEnum
from typing import Any

from fakeverse.errors import InvalidOption
from fakeverse.fakeverse import GenerationResult


class OutputFormat(StrEnum):
    """Supported output formats."""

    JSON = "json"
    NDJSON = "ndjson"
    CSV = "csv"


MEDIA_TYPES: dict[OutputFormat, str] = {
    OutputFormat.JSON: "application/json",
    OutputFormat.NDJSON: "application/x-ndjson",
    OutputFormat.CSV: "text/csv; charset=utf-8",
}


def to_json(result: GenerationResult) -> str:
    """``{"data": [...], "meta": {...}}``."""
    document = {"data": result.items, "meta": result.meta.to_dict()}
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


def to_ndjson(result: GenerationResult) -> str:
    """One item per line; metadata is not included."""
    return "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in result.items)


def flatten(item: Any) -> dict[str, Any]:
    """Flatten an item into dotted keys (``address.locality``); a scalar becomes ``value``."""
    if not isinstance(item, Mapping):
        return {"value": item}
    flat: dict[str, Any] = {}
    for key, value in item.items():
        if isinstance(value, Mapping):
            for sub_key, sub_value in flatten(value).items():
                flat[f"{key}.{sub_key}"] = sub_value
        else:
            flat[key] = value
    return flat


def to_csv(result: GenerationResult) -> str:
    """A header line, then one line per item; nulls are empty cells (RFC 4180)."""
    rows = [flatten(item) for item in result.items]
    header = list(dict.fromkeys(key for row in rows for key in row))
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    for row in rows:
        writer.writerow(["" if row.get(key) is None else row[key] for key in header])
    return buffer.getvalue()


def check_format(output: OutputFormat, *, explain: bool) -> None:
    """Check that a format accepts the options, before generating anything.

    Raises:
        InvalidOption: for ``explain`` with CSV.
    """
    if explain and output is OutputFormat.CSV:
        raise InvalidOption("The explain mode is not available with the CSV format.")


def render(result: GenerationResult, output: OutputFormat, *, explain: bool = False) -> str:
    """Render a result in a format.

    Raises:
        InvalidOption: for ``explain`` with CSV.
    """
    check_format(output, explain=explain)
    if output is OutputFormat.CSV:
        return to_csv(result)
    if output is OutputFormat.NDJSON:
        return to_ndjson(result)
    return to_json(result)
