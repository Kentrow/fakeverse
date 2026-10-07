import pytest

from fakeverse import errors

SLUGS = {
    errors.UniverseNotFound: "universe-not-found",
    errors.TypeNotSupported: "type-not-supported",
    errors.LocaleNotSupported: "locale-not-supported",
    errors.InvalidOption: "invalid-parameter",
    errors.InvalidTemplate: "invalid-template",
    errors.PoolExhausted: "pool-exhausted",
    errors.DataVersionNotFound: "data-version-not-found",
    errors.DataVersionRetired: "data-version-retired",
}


@pytest.mark.parametrize(("error", "slug"), SLUGS.items(), ids=str)
def test_slugs_are_stable(error: type[errors.FakeverseError], slug: str) -> None:
    assert issubclass(error, errors.FakeverseError)
    assert error.slug == slug
    assert error.title


def test_validation_error_without_issues() -> None:
    error = errors.UniverseValidationError([])
    assert error.issues == ()
    assert str(error) == "0 error(s) in universe files:"
