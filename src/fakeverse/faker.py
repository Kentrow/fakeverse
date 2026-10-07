"""Faker provider (extra ``faker``).

.. code-block:: python

    from faker import Faker
    from fakeverse.faker import FakeverseProvider

    fake = Faker("fr_FR")
    fake.add_provider(FakeverseProvider)
    fake.fakeverse("lotr").person()
    fake.fakeverse("lotr").unique.first_name()

Every call returns one item and draws its seed from Faker's generator, so ``Faker.seed()`` and
``fake.seed_instance()`` make sequences reproducible, for a given version of the package.
"""

from __future__ import annotations

from typing import Any

from faker.config import DEFAULT_LOCALE
from faker.providers import BaseProvider
from faker.proxy import UniqueProxy  # type: ignore[attr-defined]

from fakeverse.errors import InvalidOption, LocaleNotSupported
from fakeverse.fakeverse import Fakeverse, UniverseGenerator

_shared: Fakeverse | None = None


def shared_fakeverse() -> Fakeverse:
    """The embedded universes, loaded once on first use and shared by every provider."""
    global _shared  # noqa: PLW0603
    if _shared is None:
        _shared = Fakeverse()
    return _shared


class BoundUniverse:
    """A universe bound to a Faker generator. Each method returns a single value."""

    def __init__(self, provider: FakeverseProvider, generator: UniverseGenerator) -> None:
        self._provider = provider
        self._generator = generator
        self._unique: UniqueProxy | None = None

    @property
    def id(self) -> str:
        return self._generator.id

    @property
    def locale(self) -> str:
        """Locale actually used (the universe default when Faker's language is unsupported)."""
        return self._generator.locale

    @property
    def unique(self) -> UniqueProxy:
        """Faker's uniqueness proxy over this universe: ``.unique.first_name()``.

        Values are unique per bound universe; ``.unique.clear()`` resets them.
        """
        if self._unique is None:
            self._unique = UniqueProxy(self)
        return self._unique

    def _seed(self) -> int:
        seed: int = self._provider.generator.random.getrandbits(63)
        return seed

    def generate(self, type_id: str, **options: Any) -> Any:
        """Generate one value of any type (core or extension).

        Options: ``gender`` and ``people`` (person types), ``explain``.
        """
        return self._generator.one(type_id, self._seed(), **options)

    def template(self, template: dict[str, Any], **options: Any) -> Any:
        """Generate one row shaped by a template (options: ``explain``, ``colocate``)."""
        return self._generator.template(template, 1, self._seed(), **options).items[0]

    def person(self, **options: Any) -> dict[str, Any]:
        """A person (options: ``gender``, ``people``, ``explain``)."""
        result: dict[str, Any] = self.generate("person", **options)
        return result

    def address(self, **options: Any) -> dict[str, Any]:
        result: dict[str, Any] = self.generate("address", **options)
        return result

    def organization(self, **options: Any) -> dict[str, Any]:
        result: dict[str, Any] = self.generate("organization", **options)
        return result

    def first_name(self, **options: Any) -> Any:
        return self.generate("first_name", **options)

    def last_name(self, **options: Any) -> Any:
        return self.generate("last_name", **options)

    def full_name(self, **options: Any) -> Any:
        return self.generate("full_name", **options)

    def email(self, **options: Any) -> Any:
        return self.generate("email", **options)

    def username(self, **options: Any) -> Any:
        return self.generate("username", **options)

    def phone(self, **options: Any) -> Any:
        return self.generate("phone", **options)

    def street_address(self, **options: Any) -> Any:
        return self.generate("street_address", **options)

    def postal_code(self, **options: Any) -> Any:
        return self.generate("postal_code", **options)

    def locality(self, **options: Any) -> Any:
        return self.generate("locality", **options)

    def subdivision(self, **options: Any) -> Any:
        return self.generate("subdivision", **options)

    def area(self, **options: Any) -> Any:
        return self.generate("area", **options)

    def organization_name(self, **options: Any) -> Any:
        return self.generate("organization_name", **options)


class FakeverseProvider(BaseProvider):
    """Faker provider giving access to the Fakeverse universes: ``fake.fakeverse("lotr")``."""

    def __init__(self, generator: Any) -> None:
        super().__init__(generator)
        self._bound: dict[tuple[str, str | None, bool], BoundUniverse] = {}

    def faker_locale(self) -> str:
        """Locale of the Faker generator, ``en_US`` when it cannot be determined."""
        config = getattr(self.generator, "_Generator__config", {})
        locale: str = config.get("locale") or DEFAULT_LOCALE
        return locale

    def fakeverse(
        self, universe: str, *, locale: str | None = None, strict_locale: bool = False
    ) -> BoundUniverse:
        """Return the universe ``universe`` bound to this Faker generator.

        Args:
            universe: identifier of an embedded universe (``lotr``...).
            locale: locale to use instead of Faker's (``fr_FR`` and ``fr-FR`` both work).
            strict_locale: raise ``LocaleNotSupported`` (or ``InvalidOption`` for a malformed
                locale) instead of falling back silently to the default locale of the universe.
        """
        key = (universe, locale, strict_locale)
        if key not in self._bound:
            fakeverse = shared_fakeverse()
            wanted = locale if locale is not None else self.faker_locale()
            try:
                generator = fakeverse.universe(universe, wanted)
            except (LocaleNotSupported, InvalidOption):
                if strict_locale:
                    raise
                generator = fakeverse.universe(universe)
            self._bound[key] = BoundUniverse(self, generator)
        return self._bound[key]


__all__ = ["BoundUniverse", "FakeverseProvider", "shared_fakeverse"]
