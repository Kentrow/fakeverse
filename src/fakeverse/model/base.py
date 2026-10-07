"""Base value types of the universe format: localized texts, weighted items, identifiers."""

from __future__ import annotations

from typing import Annotated, Any, Final

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    GetJsonSchemaHandler,
    PlainValidator,
    StringConstraints,
    WithJsonSchema,
    model_validator,
)
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema, PydanticCustomError

from fakeverse.locale import LocalizedValue
from fakeverse.types import Gender

SLUG: Final[str] = r"^[a-z0-9]+(-[a-z0-9]+)*$"
SNAKE_NAME: Final[str] = r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$"
GITHUB_HANDLE: Final[str] = r"^[A-Za-z0-9]+(-[A-Za-z0-9]+)*$"

Id = Annotated[str, StringConstraints(pattern=SLUG)]
"""Identifier: lowercase letters and digits, separated by single hyphens."""

SnakeName = Annotated[str, StringConstraints(pattern=SNAKE_NAME)]
"""Name of a vocabulary or of a field, in snake_case."""

GitHubHandle = Annotated[str, StringConstraints(pattern=GITHUB_HANDLE, max_length=39)]

Weight = Annotated[int, Field(ge=1, le=1000)]
"""Draw weight, an integer from 1 to 1000."""

LOCALIZED_JSON_SCHEMA: Final[dict[str, Any]] = {
    "description": "Localized text: a string used for every locale, or a mapping from locale "
    "to string that contains the default locale.",
    "anyOf": [
        {"type": "string", "minLength": 1},
        {
            "type": "object",
            "minProperties": 1,
            "additionalProperties": {"type": "string", "minLength": 1},
        },
    ],
}


def _validate_localized(value: object) -> LocalizedValue:
    if isinstance(value, str):
        if not value.strip():
            raise PydanticCustomError("localized_empty", "Text must not be empty")
        return value
    if isinstance(value, dict) and value:
        result: dict[str, str] = {}
        for key, text in value.items():
            if not isinstance(key, str) or not isinstance(text, str) or not text.strip():
                raise PydanticCustomError(
                    "localized_mapping",
                    "Each entry of a localized mapping must map a locale to a non-empty string",
                )
            result[key] = text
        return result
    raise PydanticCustomError(
        "localized_type",
        "Expected a non-empty string or a mapping from locale to string",
    )


Localized = Annotated[
    LocalizedValue,
    PlainValidator(_validate_localized),
    WithJsonSchema(LOCALIZED_JSON_SCHEMA),
]
"""A localized text."""


def _validate_field_value(value: object) -> LocalizedValue | int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return _validate_localized(value)


FieldValue = Annotated[
    LocalizedValue | int,
    PlainValidator(_validate_field_value),
    WithJsonSchema({"anyOf": [LOCALIZED_JSON_SCHEMA, {"type": "integer"}]}),
]
"""Value of an extension item field: a localized text or an integer."""


class Model(BaseModel):
    """Base of every model of the universe format: strict and closed."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        use_attribute_docstrings=True,
    )


LONG_FORM_KEYS: Final[frozenset[str]] = frozenset({"value", "weight", "gender", "canon"})


class _Item(Model):
    value: Localized
    weight: Weight = 1

    @model_validator(mode="before")
    @classmethod
    def _expand_short_form(cls, data: Any) -> Any:
        """Turn the short form (a bare localized text) into the long form.

        A mapping is in long form when it has one of the long form keys; otherwise it is a
        localized text.
        """
        if isinstance(data, dict) and not LONG_FORM_KEYS.isdisjoint(data):
            return data
        return {"value": data}

    @classmethod
    def __get_pydantic_json_schema__(
        cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        schema = handler(core_schema)
        return {"anyOf": [LOCALIZED_JSON_SCHEMA, schema]}


class VocabItem(_Item):
    """Vocabulary entry: no origin of its own."""


class FamilyNameItem(_Item):
    """Family name entry."""

    canon: bool = True
    """False for a name invented to enrich the pool."""


class FirstNameItem(FamilyNameItem):
    """First name entry."""

    gender: Gender | None = None
    """Gender of the first name; omitted for a name usable with any gender."""
