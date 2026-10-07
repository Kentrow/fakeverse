"""Configuration of the API, from ``FAKEVERSE_*`` environment variables."""

from __future__ import annotations

import ipaddress
import re
from pathlib import Path
from typing import Final

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_RATE = re.compile(r"^\s*(\d+)\s*(?:/\s*(second|minute|hour))?\s*$")
_PERIODS: Final[dict[str, int]] = {"second": 1, "minute": 60, "hour": 3600}

type Network = ipaddress.IPv4Network | ipaddress.IPv6Network


def _split(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


class Settings(BaseSettings):
    """API settings. Lists are comma-separated strings."""

    model_config = SettingsConfigDict(env_prefix="FAKEVERSE_", extra="ignore")

    data_dir: Path | None = None
    """Directory of data snapshots ``<version>/<universe>.yaml``; the package data otherwise."""
    max_count: int = Field(default=1000, ge=1)
    max_template_leaves: int = Field(default=50, ge=1)
    rate_limit: str = "60/minute"
    """``N/second``, ``N/minute`` or ``N/hour``; ``0`` disables rate limiting."""
    rate_burst: int = Field(default=20, ge=1)
    trusted_proxies: str = ""
    """CIDRs of the proxies allowed to set ``X-Forwarded-For``."""
    disabled_universes: str = ""
    """Universes removed from the API without a rebuild (takedown procedure)."""
    cors_origins: str = "*"
    metrics_enabled: bool = False
    log_level: str = "info"

    @field_validator("rate_limit")
    @classmethod
    def _check_rate(cls, value: str) -> str:
        if _RATE.match(value) is None:
            raise ValueError("expected N/second, N/minute, N/hour or 0")
        return value

    @field_validator("trusted_proxies")
    @classmethod
    def _check_proxies(cls, value: str) -> str:
        for cidr in _split(value):
            ipaddress.ip_network(cidr, strict=False)
        return value

    @property
    def rate_per_second(self) -> float:
        """Refill rate of the token bucket; 0 when rate limiting is disabled."""
        match = _RATE.match(self.rate_limit)
        assert match is not None
        return int(match[1]) / _PERIODS[match[2] or "minute"]

    @property
    def proxy_networks(self) -> list[Network]:
        return [ipaddress.ip_network(cidr, strict=False) for cidr in _split(self.trusted_proxies)]

    @property
    def disabled(self) -> list[str]:
        return _split(self.disabled_universes)

    @property
    def cors_origin_list(self) -> list[str]:
        return _split(self.cors_origins)
