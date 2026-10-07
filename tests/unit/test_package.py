import re
from importlib.metadata import version

from typer.testing import CliRunner

import fakeverse
from fakeverse.cli import _version_callback, app

# SemVer 2.0.0 core version with optional pre-release and build metadata.
SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)

runner = CliRunner()


def test_version_is_semver() -> None:
    assert SEMVER.match(fakeverse.__version__)


def test_version_matches_installed_metadata() -> None:
    assert version("fakeverse") == fakeverse.__version__


def test_cli_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout == f"fakeverse {fakeverse.__version__}\n"


def test_cli_without_arguments_shows_help() -> None:
    result = runner.invoke(app, [])
    assert "Usage" in result.output


def test_version_callback_is_noop_when_flag_is_absent() -> None:
    _version_callback(False)
