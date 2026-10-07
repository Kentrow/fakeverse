"""Helpers of the API tests."""

from collections.abc import Callable

from fastapi.testclient import TestClient


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


type ClientFactory = Callable[..., TestClient]
